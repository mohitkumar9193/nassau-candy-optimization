"""Independent scalar checks of saved calculations and evaluation artifacts.

Standard library only; no model or simulator implementation is imported.
"""
import csv
from datetime import date
from decimal import Decimal
import itertools
import json
import math
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]


def rows(path):
    with (ROOT/path).open(newline='',encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))


def close(a,b,label,tolerance=1e-6):
    if not math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=tolerance):
        raise AssertionError(f'{label}: expected {a}, found {b}')


def truth(value):
    return str(value).lower()=='true'


def verify():
    data=rows('datasets/processed/orders_cleaned.csv')
    lookup={r['Row ID']:r for r in data}
    assert len(data)==len(lookup)==10194
    for r in data:
        close(Decimal(r['Sales'])-Decimal(r['Cost']),r['Gross Profit'],'row profit reconciliation',.01)
        days=(date.fromisoformat(r['Ship Date'])-date.fromisoformat(r['Order Date'])).days
        assert days==int(r['Order To Shipment Lead Time Days']) and 2000<=days<=2011
        assert not truth(r['Eligible For Lead Time Training'])
    assert sum(int(r['Units']) for r in data)==38654
    assert sum(Decimal(r['Sales']) for r in data)==Decimal('141783.63')
    assert sum(Decimal(r['Gross Profit']) for r in data)==Decimal('93442.80')
    assert sum(bool(r['Destination Latitude']) and bool(r['Destination Longitude']) for r in data)==9994
    for r in rows('reports/eda/tables/factory_summary.csv'):
        subset=[x for x in data if x['Assigned Factory']==r['Assigned Factory']]
        assert len(subset)==int(r['Records'])
        assert sum(int(x['Units']) for x in subset)==int(r['Units'])
        close(sum(Decimal(x['Sales']) for x in subset),r['Sales'],'factory sales')
        close(sum(Decimal(x['Gross Profit']) for x in subset),r['Gross Profit'],'factory profit')

    partitions={name:[] for name in ['train','validation','test']}
    for row in rows('reports/model_comparison/diagnostic/split_assignments.csv'):
        assert row['Order Date']==lookup[row['Row ID']]['Order Date']
        partitions[row['Partition']].append(row)
    assert [len(partitions[name]) for name in partitions]==[6519,1632,2043]
    assert max(r['Order Date'] for r in partitions['train'])<min(r['Order Date'] for r in partitions['validation'])
    assert max(r['Order Date'] for r in partitions['validation'])<min(r['Order Date'] for r in partitions['test'])
    for first,second in itertools.combinations(partitions,2):
        assert not {r['Order ID'] for r in partitions[first]} & {r['Order ID'] for r in partitions[second]}
    audit=read('reports/model_comparison/diagnostic/preprocessing_audit.json')
    for model,fits in audit.items():
        for fit_name,fit in fits.items():
            source=partitions['train']+(partitions['validation'] if fit_name=='final_pretest_fit' else [])
            records=[lookup[r['Row ID']] for r in source]
            assert fit['fitted_on_rows']==len(records)
            for index,feature in enumerate(fit['numeric_features']):
                def value(row):
                    day=date.fromisoformat(row['Order Date'])
                    return day.month if feature=='Order Month' else day.weekday() if feature=='Order Weekday' else float(row[feature]) if row[feature] else None
                values=[value(r) for r in records]
                median=statistics.median(v for v in values if v is not None)
                close(median,fit['imputer_medians'][index],model+' training median')
                filled=[median if v is None else v for v in values]
                close(statistics.fmean(filled),fit['scaled_feature_means'][index],model+' training scaler mean')
            for feature,categories in fit['training_categories'].items():
                assert set(categories)=={r[feature] for r in records}
    predictions=rows('reports/model_comparison/diagnostic/test_predictions.csv')
    for metric in rows('reports/model_comparison/diagnostic/model_metrics.csv'):
        if metric['Evaluation']!='Untouched chronological test':continue
        pred=[r for r in predictions if r['Model']==metric['Model']]
        if metric['Model']=='Training ship-mode mean (sanity baseline)':
            development=[lookup[r['Row ID']] for r in partitions['train']+partitions['validation']]
            means={mode:statistics.fmean(float(r['Order To Shipment Lead Time Days']) for r in development if r['Ship Mode']==mode) for mode in {r['Ship Mode'] for r in development}}
            pred=[{'Row ID':r['Row ID'],'Actual Source Interval Days':lookup[r['Row ID']]['Order To Shipment Lead Time Days'], 'Predicted Source Interval Days':means[lookup[r['Row ID']]['Ship Mode']], 'Diagnostic Only':'True'} for r in partitions['test']]
        assert len(pred)==2043 and {r['Row ID'] for r in pred}=={r['Row ID'] for r in partitions['test']}
        actual=[float(r['Actual Source Interval Days']) for r in pred]
        estimate=[float(r['Predicted Source Interval Days']) for r in pred]
        for r in pred:
            close(lookup[r['Row ID']]['Order To Shipment Lead Time Days'],r['Actual Source Interval Days'],'actual test target')
            assert truth(r['Diagnostic Only'])
        residual=[a-b for a,b in zip(actual,estimate)]
        sse=sum(e*e for e in residual)
        close(math.sqrt(sse/len(actual)),metric['RMSE Days'],'saved test RMSE',1e-7)
        close(statistics.fmean(abs(e) for e in residual),metric['MAE Days'],'saved test MAE',1e-7)
        mean=statistics.fmean(actual)
        close(1-sse/sum((a-mean)**2 for a in actual),metric['R2'],'saved test R2',1e-7)
    model_manifest=read('models/diagnostic/model_manifest.json')
    assert model_manifest['diagnostic_only'] and not model_manifest['operational_use_allowed']
    assert model_manifest['target_date_offset_applied']==0

    assumptions=read('datasets/simulated/logistics_assumptions.json')
    factories={r['Factory']:r for r in rows('datasets/reference/factories.csv')}
    components={}
    products=rows('datasets/reference/products.csv')
    for product in products:
        cohort=[r for r in data if r['Product ID']==product['Product ID'] and r['Destination Latitude'] and r['Destination Longitude']]
        units=sum(int(r['Units']) for r in cohort)
        sales=sum(float(r['Sales']) for r in cohort);cost=sum(float(r['Cost']) for r in cohort)
        for factory,origin in factories.items():
            lat1,lon1=map(math.radians,[float(origin['Latitude']),float(origin['Longitude'])])
            fixed=distance_cost=lead_weighted=distance_weighted=0.
            for r in cohort:
                lat2,lon2=map(math.radians,[float(r['Destination Latitude']),float(r['Destination Longitude'])])
                h=math.sin((lat2-lat1)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
                km=6371.0088*2*math.asin(math.sqrt(min(1,max(0,h))))
                planned=km*assumptions['planning_distance_multiplier'];u=int(r['Units'])
                mode=assumptions['ship_modes'][r['Ship Mode']]
                fixed+=(assumptions['handling_cost_per_record']+u*assumptions['logistics_cost_per_unit'])*mode['cost_multiplier']
                distance_cost+=u*planned/1000*assumptions['distance_cost_per_unit_per_1000_km']*mode['cost_multiplier']
                lead_weighted+=u*(assumptions['factories'][factory]['dispatch_preparation_days']+mode['dispatch_preparation_days']+planned/1000*assumptions['dispatch_coordination_days_per_1000_km'])
                distance_weighted+=u*km
            components[product['Product ID'],factory]=(fixed,distance_cost,lead_weighted/units,distance_weighted/units,sales,cost)
    scenarios=rows('reports/scenario_simulator/scenarios.csv')
    assert len(scenarios)==75
    by_scenario={r['Scenario ID']:r for r in scenarios}
    for row in scenarios:
        current=components[row['Product ID'],row['Current Factory']]
        candidate=components[row['Product ID'],row['Candidate Factory']]
        same=truth(row['Is Current Assignment'])
        multiplier=1 if same else assumptions['factories'][row['Candidate Factory']]['alternative_manufacturing_cost_multiplier']
        delta=current[0]+current[1]-candidate[0]-candidate[1]+current[5]*(1-multiplier)-(0 if same else assumptions['one_time_reassignment_cost_per_product'])
        close(delta,row['Modeled Contribution Change'],'independent base contribution')
        close(candidate[3],row['Candidate Weighted Great Circle Km'],'independent great circle distance')
        close(current[2]-candidate[2],row['Modeled Dispatch Lead Reduction Days'],'independent dispatch reduction')
    sensitivity=rows('reports/scenario_simulator/sensitivity.csv')
    assert len(sensitivity)==6075
    for row in sensitivity:
        scenario=by_scenario[row['Scenario ID']]
        current=components[scenario['Product ID'],scenario['Current Factory']]
        candidate=components[scenario['Product ID'],scenario['Candidate Factory']]
        same=truth(scenario['Is Current Assignment'])
        multiplier=1 if same else assumptions['factories'][scenario['Candidate Factory']]['alternative_manufacturing_cost_multiplier']*float(row['Alternative Manufacturing Multiplier'])
        rate=float(row['Distance Rate Multiplier'])
        delta=current[0]+current[1]*rate-candidate[0]-candidate[1]*rate+current[5]*(1-multiplier)-(0 if same else assumptions['one_time_reassignment_cost_per_product']*float(row['Setup Cost Multiplier']))
        close(delta,row['Modeled Contribution Change'],'independent sensitivity contribution')
    selected=rows('reports/recommendations/selected_rows.csv')
    moves=[r for r in selected if not truth(r['Is Current Assignment'])]
    assert len(selected)==15 and len(moves)==5
    assert all(float(r['Modeled Contribution Change'])>=0 and float(r['Ranking Score'])>0 for r in moves)
    assert all(not truth(r['Operationally Supported']) and float(r['Scenario Confidence Score'])==0 for r in selected)
    kpis=read('reports/recommendations/kpis.json')
    lead=100*sum(float(r['Mapped Units'])*float(r['Modeled Dispatch Lead Reduction Days']) for r in selected)/sum(float(r['Mapped Units'])*float(r['Current Modeled Dispatch Lead Days']) for r in selected)
    close(lead,kpis['modeled_lead_time_reduction_pct'],'portfolio lead KPI')
    ids={r['Scenario ID'] for r in moves}
    joint={case:sum(float(r['Modeled Contribution Change']) for r in sensitivity if int(r['Case'])==case and r['Scenario ID'] in ids) for case in range(1,82)}
    close(sum(value>=-1e-9 for value in joint.values())/81*100,kpis['profit_impact_stability_pct'],'joint stability KPI')
    close(min(joint.values()),kpis['sensitivity_min_portfolio_contribution_change'],'joint downside')
    close(sum(float(r['Modeled Contribution Change']) for r in moves),kpis['base_modeled_contribution_change'],'base contribution KPI')
    close(100*len(moves)/len(selected),kpis['recommendation_coverage_pct'],'coverage KPI')
    policy=read('datasets/reference/recommendation_policy.json')
    for row in rows('reports/recommendations/ranked_options.csv'):
        speed=max(-1,min(1,float(row['Modeled Dispatch Lead Reduction Pct'])/policy['speed_reference_reduction_pct']))
        profit=max(-1,min(1,float(row['Modeled Contribution Change'])/max(abs(float(row['Current Modeled Contribution']))*policy['profit_reference_change_pct']/100,policy['profit_scale_floor_source_units'])))
        score=float(row['Speed Priority'])*speed+float(row['Profit Priority'])*profit-policy['stability_penalty_weight']*(1-float(row['Profit Impact Stability Pct'])/100)
        close(score,row['Ranking Score'],'independent weighted ranking score')
    result={'status':'passed','records_reconciled':len(data),'chronological_partitions':[6519,1632,2043],
            'test_metric_models_recomputed':4,'scenario_pairs_recomputed':75,'sensitivity_cases_recomputed':6075,
            'ranking_scores_recomputed':75,'portfolio_kpis_recomputed':True,'date_anomaly_preserved':True,
            'operational_model_created':False}
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':verify()
