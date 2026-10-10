"""Build submission PDFs and editable Markdown from the completed project exports.

Run from the repository root: python reports/submission/build_documents.py
Requires reportlab plus the existing pandas/numpy/matplotlib analysis dependencies.
"""
import csv
from html import escape, unescape
import json
from pathlib import Path
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
FIGURES=OUT/'figures'
WIDTH=504


def read_csv(relative):
    with (ROOT/relative).open(newline='',encoding='utf-8') as stream:
        return list(csv.DictReader(stream))


def load_json(relative):
    return json.loads((ROOT/relative).read_text(encoding='utf-8'))


def n(value, digits=2):
    return f'{float(value):,.{digits}f}'


def fonts():
    folder=Path('C:/Windows/Fonts')
    if (folder/'times.ttf').exists():
        for name,filename in [('Body','times.ttf'),('BodyBold','timesbd.ttf'),('BodyItalic','timesi.ttf'),('Heading','arial.ttf'),('HeadingBold','arialbd.ttf')]:
            pdfmetrics.registerFont(TTFont(name,str(folder/filename)))
        pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold',italic='BodyItalic',boldItalic='BodyBold')
        pdfmetrics.registerFontFamily('Heading',normal='Heading',bold='HeadingBold',italic='Heading',boldItalic='HeadingBold')
        return 'Body','Heading'
    return 'Times-Roman','Helvetica'


BODY,HEADING=fonts()
STYLES={
    'body':ParagraphStyle('Body',fontName=BODY,fontSize=11.2,leading=15.2,spaceAfter=8,textColor=colors.black),
    'title':ParagraphStyle('Title',fontName=HEADING,fontSize=22,leading=26,spaceAfter=14,textColor=colors.black),
    'subtitle':ParagraphStyle('Subtitle',fontName=HEADING,fontSize=11,leading=15,spaceAfter=16,textColor=colors.black),
    'heading':ParagraphStyle('Heading',fontName=HEADING,fontSize=14,leading=18,spaceBefore=12,spaceAfter=9,textColor=colors.black,keepWithNext=True),
    'smallheading':ParagraphStyle('SmallHeading',fontName=HEADING,fontSize=11.5,leading=15,spaceBefore=9,spaceAfter=6,textColor=colors.black,keepWithNext=True),
    'caption':ParagraphStyle('Caption',fontName=BODY,fontSize=9.5,leading=12.2,spaceBefore=4,spaceAfter=9,textColor=colors.black),
    'cell':ParagraphStyle('Cell',fontName=BODY,fontSize=9.4,leading=12,textColor=colors.black),
    'headcell':ParagraphStyle('HeaderCell',fontName=HEADING,fontSize=9,leading=11.5,textColor=colors.black),
    'reference':ParagraphStyle('Reference',fontName=BODY,fontSize=9.6,leading=12.8,spaceAfter=8,textColor=colors.black),
}


class Manuscript:
    def __init__(self,name,title,subtitle):
        self.name=name; self.title=title; self.story=[]; self.md=[]
        self.story.extend([Paragraph(escape(title),STYLES['title']),Paragraph(escape(subtitle),STYLES['subtitle'])])
        self.md.extend(['# '+title,'',subtitle,''])
    def heading(self,title,level=1):
        self.story.append(Paragraph(escape(title),STYLES['heading' if level==1 else 'smallheading']))
        self.md.extend(['#'*(level+1)+' '+title,''])
    def paragraph(self,text,kind='body'):
        self.story.append(Paragraph(text,STYLES[kind]))
        plain=text.replace('<b>','**').replace('</b>','**').replace('<i>','*').replace('</i>','*')
        plain=re.sub(r'<link href="([^"]+)">(.*?)</link>',r'[\2](\1)',plain)
        self.md.extend([unescape(re.sub(r'<[^>]+>','',plain)),''])
    def table(self,headers,rows,widths,caption=None,numeric=()):
        if caption: self.paragraph(caption,'caption')
        content=[[Paragraph(escape(str(v)),STYLES['headcell']) for v in headers]]
        content += [[Paragraph(escape(str(v)),ParagraphStyle('NumericCell',parent=STYLES['cell'],alignment=TA_RIGHT) if column in numeric else STYLES['cell']) for column,v in enumerate(row)] for row in rows]
        table=Table(content,colWidths=widths,repeatRows=1,hAlign='LEFT')
        commands=[('GRID',(0,0),(-1,-1),.45,colors.HexColor('#D9D9D9')),
                  ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E9EFF5')),
                  ('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),7),
                  ('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),4.5),('BOTTOMPADDING',(0,0),(-1,-1),4.5)]
        for index in numeric: commands.append(('ALIGN',(index,1),(index,-1),'RIGHT'))
        table.setStyle(TableStyle(commands)); self.story.extend([table,Spacer(1,10)])
        self.md.extend(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |'])
        self.md.extend('| '+' | '.join(map(str,row))+' |' for row in rows); self.md.append('')
    def figure(self,path,caption,max_height=230):
        width,height=ImageReader(str(path)).getSize()
        scale=min(WIDTH/width,max_height/height)
        self.story.append(KeepTogether([Image(str(path),width*scale,height*scale),Paragraph(escape(caption),STYLES['caption'])]))
        self.md.extend([f'![{caption}](figures/{path.name})',''])
    def new_page(self):
        self.story.append(PageBreak()); self.md.extend(['<!-- Page break -->',''])
    def save(self):
        def footer(canvas,document):
            canvas.saveState(); canvas.setFont(HEADING,8); canvas.setFillColor(colors.black)
            canvas.drawString(54,34,'Nassau Candy internship analysis | 10 October 2026')
            canvas.drawRightString(558,34,str(document.page)); canvas.restoreState()
        doc=SimpleDocTemplate(str(OUT/(self.name+'.pdf')),pagesize=(612,792),leftMargin=54,rightMargin=54,topMargin=45,bottomMargin=54,
                              title=self.title,author='',subject='Independent educational analysis with explicitly hypothetical planning scenarios')
        doc.build(self.story,onFirstPage=footer,onLaterPages=footer)
        (OUT/(self.name+'.md')).write_text('\n'.join(self.md),encoding='utf-8')


def make_figures(queue,joint,kpis):
    FIGURES.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.unicode_minus':False,'savefig.dpi':180})
    persistent=[row for row in queue if row['Persistent Long Distance'].lower()=='true']
    labels=[row['Product Name'].replace('Wonka Bar - ','')+' / '+row['Region'] for row in persistent]
    values=[float(row['Unit Weighted Distance Km']) for row in persistent]
    fig,ax=plt.subplots(figsize=(7.5,3.3)); ax.barh(labels,values,color='#405C78');ax.invert_yaxis()
    ax.set_xlabel('Unit-weighted great-circle distance (km)');ax.set_xlim(0,4000)
    ax.spines[['top','right']].set_visible(False)
    for i,value in enumerate(values):ax.text(value+35,i,f'{value:,.0f}',va='center',fontsize=9)
    fig.tight_layout();fig.savefig(FIGURES/'geographic_priorities.png',facecolor='white');plt.close(fig)
    changes=sorted(float(row['Portfolio Contribution Change']) for row in joint)
    fig,ax=plt.subplots(figsize=(7.5,2.7));ax.plot(range(1,len(changes)+1),changes,color='#405C78',linewidth=2)
    ax.axhline(0,color='#555555',linewidth=.8);ax.axhline(kpis['base_modeled_contribution_change'],color='#8F5B25',linestyle='--',linewidth=1,label='Base modeled change')
    ax.set_xlabel('Sorted sensitivity case rank (81 cases)');ax.set_ylabel('Contribution change\n(source monetary units)')
    ax.spines[['top','right']].set_visible(False);ax.legend(loc='upper left',frameon=False,fontsize=9)
    fig.tight_layout();fig.savefig(FIGURES/'joint_sensitivity.png',facecolor='white');plt.close(fig)


def research(factory,regions,modes,metrics,queue,selected,kpis,products,coordinates):
    paper=Manuscript('research_paper','Factory Reallocation and Shipping Optimization Recommendation System for Nassau Candy Distributor',
                     'Research paper | Data analytics internship submission | Analysis snapshot 10 October 2026')
    paper.heading('Abstract')
    paper.paragraph('This applied study evaluates factory assignments in a public educational candy-distributor sample containing 10,194 records, 38,654 units, 15 products and five factories. Descriptive analysis identifies concentrated chocolate demand and substantial geographic exposure. However, every source order-to-shipment interval is 2,000-2,011 days; the target is unverified and no operational prediction model can be validated. Linear Regression, Random Forest and Gradient Boosting were therefore compared only as diagnostics using chronological splits and preprocessing fitted within training partitions. Linear Regression was selected on validation accuracy and interpretability, with test RMSE 0.9976 days on the anomalous target.')
    paper.paragraph('A separate simulator uses explicitly hypothetical dispatch and logistics assumptions. At the default equal speed/profit priority, five chocolate products are proposed for investigation at Secret Factory. The modeled portfolio dispatch reduction is 4.06%, base contribution change is +977.68 source monetary units, and contribution is nonnegative in 66.67% of the 81 tested joint sensitivity cases. Evidence readiness and verified recommendation coverage are both zero. The study supports targeted data collection and geographic review; it does not establish feasible reassignments, delivery improvements or realized profit gains.')
    paper.heading('Research purpose')
    paper.paragraph('The assignment asks which products should be reassigned to improve shipping performance while protecting profitability. This paper examines three questions: where current demand and geographic exposure concentrate; how well the requested regressors fit the available date intervals; and which alternate assignments deserve investigation under transparent, adjustable assumptions.')
    paper.heading('Scope of the evidence')
    paper.paragraph('Observed sample financials and source dates, static reference assignments, and simulated outcomes are reported separately. The unit of analysis is a source record, not necessarily a distinct order. Repeated Order IDs are retained because the transaction grain is ambiguous. The sample is not verified proprietary Nassau Candy operating data, and no official company or government endorsement is claimed. [1, 4]')

    paper.new_page();paper.heading('Data provenance and validation')
    paper.paragraph('The Maven Analytics US Candy Distributor archive supplies the 18 required order fields and reference tables. Its publisher labels the dataset Public Domain. Source bytes are preserved with SHA-256 hashes. Factory coordinates and product assignments supplied in the internship brief are reconciled through documented spelling aliases. US destination coordinates come from the historical SimpleMaps ZIP snapshot packaged in the archive; the Basic geography attribution is retained under CC BY 4.0. Current website summary counts are not substituted for the actual downloaded file counts. [1, 2, 4]')
    paper.table(['Validation measure','Result'],[
        ['Primary cleaned records','10,194'],['Missing required cells and exact duplicate removals','0 and 0'],
        ['Product names standardized and division labels corrected','2,064 and 6'],['Extreme cost records flagged and retained','5'],
        ['Source intervals outside the 60 day quality screen','10,194'],['Shipment dates after the analysis snapshot','9,824'],
        ['Verified historical lead time training records','0'],['Mapped records and mapped unit coverage','9,994 records and 97.98% of units']],
        [340,164],caption='Table 1  Validation results from the cleaning and geography exports')
    paper.paragraph('Money is checked as finite decimal values, units as positive integers, and gross profit against sales minus manufacturing cost with tolerance 0.01. Identifiers and postal codes remain text. Only exact duplicates are removable; no duplicates or conflicting Row IDs required removal. Six Fizzy Lifting Drinks division labels were corrected to Other. [4]')
    paper.paragraph('Outer Tukey fences at three times the interquartile range flag extreme values within relevant product, ship-mode or country groups. Groups below 20 observations or with zero IQR are unassessed. The five flagged cost records are retained in primary EDA, with a separate 10,189-record sensitivity subset. Excluding them changes sales by -0.18% and gross profit by -0.19%, so the reported aggregate concentration is not driven by these five records. [4, 5]')
    paper.paragraph('<b>Date interpretation.</b> Ship Date minus Order Date measures the interval until shipment. Delivery dates are absent. All intervals fail the explicit 60-day screen; no assumed 2,000-day correction is applied. A systematic shift can evade relative outlier screening, so this quality failure is treated separately. [4]')

    paper.new_page();paper.heading('Demand sales and profitability')
    paper.paragraph('Orders span 3 January 2021 to 30 December 2024. Across the full cleaned population, sales total 141,783.63, manufacturing cost 48,340.83 and source gross profit 93,442.80, in unspecified source monetary units. Gross margin is 65.91%. These source profits exclude freight, reassignment expense and other operating costs. Chocolate represents 96.43% of units and 92.88% of sales, making its five products the largest-demand scope for further investigation. [5]')
    paper.table(['Assigned factory','Units','Sales','Gross profit','Margin'],[
        [r['Assigned Factory'],n(r['Units'],0),n(r['Sales']),n(r['Gross Profit']),n(r['Gross Margin Pct'])+'%'] for r in factory],
        [140,62,108,108,86],caption='Table 2  Source financials by static assigned factory  Monetary columns use source units',numeric=(1,2,3,4))
    paper.paragraph("Lot's O' Nuts accounts for 55.39% of units and Wicked Chocy's for 41.04%. Together, their chocolate assignments dominate the sample. These totals are reference-based allocations, not measurements of factory production or capacity utilization. Secret Factory has 884 statically assigned units in the sample; its current support should not be interpreted as spare production capacity. [5]")
    paper.table(['Destination region','Units','Sales','Sales share'],[
        [r['Region'],n(r['Units'],0),n(r['Sales']),n(r['Sales Share Pct'])+'%'] for r in regions],
        [180,90,135,99],caption='Table 3  Demand and sales by destination region',numeric=(1,2,3))
    paper.paragraph('Pacific is the largest sales region at 32.66%, followed by Atlantic at 29.06%. Sample annual sales rise from 28,953.55 in 2021 to 46,968.11 in 2024, a descriptive increase of 62.22%. Completeness and comparability of the business sample are not established, so this is not a causal growth estimate. Kazookles has the lowest product gross margin, 7.69%, reinforcing the need to evaluate transition costs before considering a low-margin product move. [5]')

    paper.new_page();paper.heading('Shipping modes geography and route investigation')
    paper.table(['Ship mode','Records','Units','Demand share'],[
        [r['Ship Mode'],n(r['Records'],0),n(r['Units'],0),n(r['Demand Share Pct'])+'%'] for r in modes],
        [185,90,100,129],caption='Table 4  Mode labels describe demand allocation  They do not verify service speed',numeric=(1,2,3))
    paper.paragraph('Standard Class carries 60.56% of units. No mode has validated historical lead-time observations. Haversine great-circle distances use static factory coordinates and destination ZIP centroids. Coordinates cover 98.04% of records; all 200 Canadian records remain in source financial totals but are excluded from geographic scenarios. The mapped unit-weighted distance is 2,003.8 km. These distances are not actual road routes, transport costs or emissions. [5, 6]')
    paper.paragraph('Routes are product by assigned factory by destination country by region by ship mode. Of 180 routes, 77 meet at least 20-record support and 90% coordinate coverage, covering 9,623 records. Geographic KMeans uses standardized distance, within-route distance variability and log-transformed demand; three clusters have silhouette 0.401. A separate four-feature diagnostic adds the unverified mean and standard deviation of date intervals, selecting two clusters with silhouette 0.474. Candidate cluster counts 2-6, seed 42 and 20 initializations are documented. Additional tested seeds reproduce the assignments, which checks initialization stability rather than business validity. [6]')
    paper.figure(FIGURES/'geographic_priorities.png','Figure 1  Five persistent geographic review candidates  Each exceeds the 2,697.4 km screen in all 16 supported quarters  Distance is geographic exposure only',max_height=210)
    paper.paragraph('Seven combinations meet the geographic screen; five are persistently distant. Investigate the two Pacific and three Atlantic flows in Figure 1 first. The two Gulf candidates are less persistent. Confirmed slow-route detection is unavailable; the empty export does not prove that slow routes are absent. Congestion cannot be established from these data. [6]')

    paper.new_page();paper.heading('Prediction models and chronological evaluation')
    paper.paragraph('The unchanged source date interval is the diagnostic target. Numerical features are units, great-circle distance, order month and weekday. Categorical features are Product ID, assigned factory, region and ship mode. Median imputation with a missing indicator and numerical standardization, plus most-frequent categorical imputation and one-hot encoding, are fitted inside training pipelines. Source geography is never filled with a zero distance. Target-derived fields, shipment dates, IDs and financial outcomes are excluded. [3, 7]')
    paper.table(['Partition','Records','Order date range'],[
        ['Initial training','6,519','2021-01-03 to 2023-12-04'],['Validation','1,632','2023-12-05 to 2024-07-17'],
        ['Untouched test','2,043','2024-07-18 to 2024-12-30']], [145,70,289],caption='Table 5  Whole dates and repeated Order IDs stay within a single partition',numeric=(1,))
    paper.paragraph('Training-only three-IQR quantity and interval screens exclude zero records. Validation and test records are untrimmed. Final preprocessing fits only pretest development after selection. Linear Regression uses ordinary least squares. Random Forest has 160 trees, depth 10 and minimum leaf size 4. Gradient Boosting has 160 trees, learning rate 0.05, depth 2 and minimum leaf size 4. Seeds are fixed at 42; test results do not tune parameters. [7]')
    paper.table(['Model and evaluation','RMSE days','MAE days','R2'],[
        [r['Model'].replace('Training ship-mode mean (sanity baseline)','Ship mode mean baseline')+' / '+('validation' if r['Evaluation']=='Chronological validation' else 'test'),n(r['RMSE Days'],4),n(r['MAE Days'],4),n(r['R2'],4)] for r in metrics],
        [264,80,80,80],caption='Table 6  Diagnostic fit to anomalous date intervals  Errors are not verified shipping errors',numeric=(1,2,3))
    paper.paragraph('RMSE penalizes larger errors, MAE reports average absolute error, and R2 compares explained variance with a holdout mean baseline. Linear Regression is selected on validation RMSE and a predefined interpretability rule favoring it within 5% of the best validation RMSE. It is then refitted on pretest development. Gradient Boosting has marginally lower test RMSE, but this does not justify selecting it after viewing the test. The simple training ship-mode mean has similar RMSE and lower MAE than the requested models. [3, 7]')

    paper.new_page();paper.heading('Interpretability and the scenario design')
    paper.paragraph('Raw-feature permutation importance for the selected diagnostic model shows ship mode increasing MAE by 0.9842 days when shuffled, versus 0.0077 days for distance and 0.0042 days for assigned factory. These values describe association with the suspect target. Product and factory are coupled because each product has only one static assigned factory. Linear coefficients cannot identify independent factory effects, and nonlinear tree models cannot validate an unseen alternate factory-product combination from this assignment structure. No diagnostic model is used in the operational simulator. [7]')
    paper.heading('Explicit hypothetical assumptions',2)
    paper.paragraph('The simulator compares 75 product-factory scenarios: 15 current assignments and 60 alternatives. It replays identical mapped destination records, units and ship modes for each pair. Planning distance is 1.15 times Haversine distance, a planning proxy rather than measured road distance. Logistics per record comprises handling of 0.04, 0.03 per unit and 0.06 per unit per 1,000 planning km, multiplied by an assumed mode cost factor. Currency is unspecified. [8]')
    paper.paragraph('Assumed dispatch allowance is factory preparation plus ship-mode preparation plus 0.15 days per 1,000 planning km. The distance term is a hypothetical pre-shipment coordination buffer, not vehicle travel time. Every factory has base preparation of 0.75 days and a neutral alternative manufacturing multiplier of 1.0. Mode preparation assumptions are 1.25, 0.75, 0.35 and 0.05 days for Standard, Second, First and Same Day respectively. [8]')
    paper.paragraph('Current manufacturing expense remains source cost. Candidate expense is source cost multiplied by the candidate manufacturing assumption. Modeled contribution subtracts manufacture, assumed logistics and a one-time setup cost of 100 for each alternative product-factory assignment. It is not actual net profit and omits tax, overhead, inventory and unmeasured transition effects. Handling is per source record because Order ID grain is ambiguous. The entire assumed setup cost is charged to the mapped cohort. [8]')
    paper.table(['Sensitivity factor','Tested multipliers'],[
        ['Distance logistics rate','0.75, 1.00, 1.50'],['Alternative manufacturing cost','0.95, 1.00, 1.10'],
        ['One time setup cost','0.50, 1.00, 2.00'],['Dispatch coordination buffer','0.75, 1.00, 1.50']],
        [285,219],caption='Table 7  Cartesian sensitivity grid  81 cases per scenario and 6,075 cases overall')
    paper.paragraph('Common distance-rate and dispatch-buffer shocks apply to baseline and candidate; alternative manufacturing and setup factors apply to reassignment. There are 16 alternatives with positive base contribution and 36 with shorter assumed dispatch allowance, but none preserves contribution across every tested case. Bounds reflect tested assumptions, not statistical confidence intervals or probabilities. [8]')

    paper.new_page();paper.heading('Ranking logic and the default portfolio')
    paper.paragraph('Speed utility divides modeled dispatch reduction percent by 10. Profit utility divides contribution change by the larger of 5% of absolute current modeled contribution or 100 source monetary units. Both utilities are clipped between -1 and 1. The score combines their weights and subtracts 0.1 times one minus the product sensitivity stability fraction. These scales and the risk penalty are declared heuristics, not learned or calibrated coefficients. [9]')
    paper.paragraph('The default uses 50% speed and 50% profit priority and blocks base contribution losses. Strict protection requires nonnegative change in every tested case; an explicit tradeoff policy permits base losses. Positive-score eligible alternatives are ranked per product. A greedy joint portfolio rechecks receiving capacity once per product and conservatively does not reuse released origin units. Top-three alternative lists are standalone comparisons, not a jointly feasible plan or global optimum. [9]')
    moves=[r for r in selected if r['Is Current Assignment'].lower()=='false']
    paper.table(['Chocolate product','Current factory','Dispatch reduction','Contribution change'],[
        [r['Product Name'].replace('Wonka Bar - ',''),r['Current Factory'],n(r['Modeled Dispatch Lead Reduction Pct'])+'%',n(r['Modeled Contribution Change'])] for r in moves],
        [164,135,103,102],caption='Table 8  Five provisional moves all target Secret Factory  Every scenario confidence score is zero',numeric=(2,3))
    paper.table(['KPI','Definition and default result'],[
        ['Modeled dispatch reduction','Mapped-unit weighted saved dispatch days divided by current modeled days across the portfolio including retained assignments: 4.06%.'],
        ['Profit impact stability','Nonnegative summed reassignment contribution under aligned common shocks: 54 of 81 cases, or 66.67%.'],
        ['Scenario confidence','Mapped-unit weighted minimum evidence gate across proposed moves: 0 of 100. It is not a probability.'],
        ['Provisional recommendation coverage','5 proposed products / 15 assessed products: 33.33%.'],
        ['Verified recommendation coverage','0 evidence-supported products / 15 assessed products: 0%.']],
        [150,354],caption='Table 9  Required KPI definitions retain the distinction between scenario utility and evidence')
    paper.paragraph('The evidence gate takes the minimum of verified-date coverage, observed-origin coverage, alternative-outcome support, verified capacity, verified compatibility and calibrated nonsimulated estimate availability. Missing evidence prevents readiness from rising solely because the mathematical score is positive. Ten products retain their assignments. Default selections are unchanged at the five exported speed priorities 0, 25, 50, 75 and 100%; scores and comparison ordering change. Strict all-case protection selects no moves, making reassignment stability and readiness not applicable. [9]')

    paper.new_page();paper.heading('Sensitivity feasibility and limitations')
    paper.paragraph('The five selected moves give a base modeled contribution change of +977.68 source monetary units over the mapped 2021-2024 replay. Joint changes range from -4,090.69 to +4,066.00 in the chosen sensitivity grid. Cases use aligned common shocks across products; stability is computed from their summed changes, not from an average of individual product stability percentages. The dispatch-buffer axis does not change contribution, so financial outcomes repeat across its three levels. Grid-case counts do not represent empirical outcome probabilities. [9]')
    paper.figure(FIGURES/'joint_sensitivity.png','Figure 2  Sorted joint contribution changes for 81 sensitivity cases  Case rank is not time or an estimated probability distribution',max_height=205)
    paper.paragraph('All five proposals target Secret Factory and reserve 37,275 whole-product sample units, including unmapped demand, at the receiver. Its baseline static assignment totals only 884 units; neither number measures physical capacity. This concentration makes verified production capability and additional capacity essential before any full reassignment. Capacity inputs mean additional units beyond baseline over the complete replay, not units per day. Null means unknown, zero means no added capacity, and an empty compatibility list blocks all products. No capacity or compatibility was invented. [9]')
    paper.heading('Limits on interpretation',2)
    paper.paragraph('This educational sample does not establish population representativeness, actual shipment origins, validated dispatch targets, delivery dates, road routing, observed tariffs or alternative-factory outcomes. Canadian exclusions and ZIP centroid approximation restrict geographic coverage. Static product-factory coupling prevents causal attribution, while sparse products limit generalization. Neutral cost assumptions and the chosen setup cost can strongly influence rankings. Factory capacity, capability, service obligations and transition risks remain unverified. [4-9]')
    paper.paragraph('Consequently, the observed geographic exposure does not prove congestion, and the assumed dispatch gain does not establish delivery acceleration. Source gross profit is not net profit. No emissions, employment, tax-revenue or public-return estimate is supported by the available variables. These quantities would require their own measurements and evaluation design.')

    paper.new_page();paper.heading('Recommendations and conclusion')
    paper.paragraph('First, resolve the date anomaly with the source owner and capture observed shipment origins and delivery milestones. Retain original values and document any verified correction. Repeat chronological training only after valid targets exist; validate lead-time prediction separately from reassignment effects. Next, investigate the five persistent long-distance product-region flows, collecting actual routes and tariffs rather than treating great-circle distance as operating expense. [4, 6, 7]')
    paper.paragraph('Before a factory trial, verify product capability, additional capacity over a stated horizon, manufacturing differences, setup and inventory costs. Recalculate scenarios with those inputs and compare against retaining the current assignment. A limited, monitored trial is a proposed next step only after these checks. For evaluation, record actual dispatch and delivery times, fully scoped costs and retained-product baselines. Report uncertainty and any service deterioration alongside gains; do not infer feasibility from a favorable planning score. [8, 9]')
    paper.paragraph('For government stakeholders, the relevant output is an auditable example of logistics analytics and a proposed evidence-collection process. The results do not justify plant-relocation incentives, freight-capacity investment, emissions claims or budgeted savings. Stakeholder review should request the assumptions, data provenance and verified constraints before considering a broader pilot.')
    paper.paragraph('The project delivers reproducible EDA, diagnostic model comparisons, route investigation, explicit scenario assumptions and a functioning Streamlit decision interface. Its strongest quantitative conclusions concern sample demand, financial concentration and geography. The five default proposals are useful investigation priorities, while zero evidence readiness preserves the central finding that actual reassignment performance remains unvalidated.')
    paper.heading('Reproducibility and application status',2)
    paper.paragraph('The source package contains Python 3.12 dependency locks, original-file hashes, audit exports, tests and deployment guides. An independently extracted package reproduced the saved scenario KPIs and passed 24 analytics/dashboard tests. The dashboard provides product, region and mode filters, a speed/profit slider, ranked alternatives, risk alerts and CSV/JSON/ZIP downloads. A static Vercel companion presents completed exports. Remote GitHub and account deployments have not been performed. [10]')
    paper.paragraph('From the repository root, install the analysis dependency lock and run <i>python analysis/reproduce.py --diagnostic-models</i>. Diagnostic model bundles explicitly prohibit operational use. The scenario engine uses its own assumption file; the regression artifacts never supply its factory reassignment estimates.')

    paper.new_page();paper.heading('References and analysis evidence')
    references=[
        '[1] Maven Analytics. US Candy Distributor dataset. Public educational sample; publisher states Public Domain. Retrieved 10 October 2026. <link href="https://mavenanalytics.io/data-playground/us-candy-distributor">https://mavenanalytics.io/data-playground/us-candy-distributor</link>. Source archive and exact raw-file hashes: datasets/source_manifest.json.',
        '[2] SimpleMaps. US ZIP Codes Database, Basic geography, CC BY 4.0. Historical snapshot included in the Maven archive. <link href="https://simplemaps.com/data/us-zips">https://simplemaps.com/data/us-zips</link>; <link href="https://creativecommons.org/licenses/by/4.0/">https://creativecommons.org/licenses/by/4.0/</link>. Joined coordinates and derived great-circle distances preserve attribution.',
        '[3] Scikit-learn 1.9.1 documentation. Common pitfalls and recommended practices; Metrics and scoring. Accessed 10 October 2026. <link href="https://scikit-learn.org/stable/common_pitfalls.html#data-leakage">https://scikit-learn.org/stable/common_pitfalls.html#data-leakage</link>; <link href="https://scikit-learn.org/stable/modules/model_evaluation.html#regression-metrics">https://scikit-learn.org/stable/modules/model_evaluation.html#regression-metrics</link>. Referenced for preprocessing leakage safeguards and regression metric interpretation.',
        '[4] Project validation exports. datasets/DATASET_GUIDE.md; datasets/cleaning_validation_summary.json; datasets/processed/cleaning_audit.csv; reports/data_cleaning_report.md. Original raw values, required field checks, label normalization, date flags and outlier screens.',
        '[5] Project EDA exports. reports/eda/current_performance_report.md; reports/eda/tables/factory_summary.csv; region_summary.csv; ship_mode_summary.csv; division_summary.csv; product_summary.csv; year_summary.csv; outlier_sensitivity.csv. All listed CSVs are in reports/eda/tables/.',
        '[6] Project route investigation. reports/route_analysis/route_investigation_report.md; route_analysis_summary.json; region_product_investigation_queue.csv. Methods and geographic support rules in analysis/cluster_routes.py.',
        '[7] Project diagnostic model comparison. reports/model_comparison/diagnostic/model_metrics.csv; split_assignments.csv; selected_model_permutation_importance.csv; model_comparison_report.md. All listed files are in that diagnostic directory. Training logic: analysis/train_compare_models.py.',
        '[8] Project scenario simulator. datasets/simulated/logistics_assumptions.json; reports/scenario_simulator/scenario_simulator_report.md; scenarios.csv; sensitivity.csv. Simulator logic: analysis/scenario_simulator.py.',
        '[9] Project recommendation exports. reports/recommendations/kpis.json; selected_rows.csv; portfolio.csv; joint_portfolio_sensitivity.csv; priority_sweep_kpis.csv; recommendation_report.md. Constraints: datasets/reference/operational_constraints.json. Ranking policy and logic are documented in the reference policy JSON and analysis/rank_recommendations.py.',
        '[10] Project verification and deployment. reports/dashboard_validation.md; reports/deployment_readiness.md; deployment/README.md; dashboard/app.py; analysis/tests/. The recorded checks concern software reproducibility, not validated shipping performance.'
    ]
    for item in references:paper.paragraph(item,'reference')
    paper.heading('Evidence traceability',2)
    paper.paragraph('Tables 1-4 use validation and EDA exports; Table 5 and Table 6 use split and metric exports; Table 7 uses the explicit assumption grid; Tables 8-9 and Figure 2 use default recommendation exports. Figure 1 uses persistent rows in the region-product investigation queue. Monetary amounts remain in source units because the downloaded dictionary does not identify a currency. The build script reads the actual CSV and JSON exports for displayed tables and figures. No new shipping observations are generated.')

    paper.new_page();paper.heading('Appendix reference inputs')
    paper.paragraph('The 18 required fields are Row ID, Order ID, Order Date, Ship Date, Ship Mode, Customer ID, Country/Region, City, State/Province, Postal Code, Division, Region, Product ID, Product Name, Sales, Units, Gross Profit and Cost. The enriched copy adds reference provenance, coordinates, calculated intervals and validation flags while preserving original source files. [4]')
    paper.table(['Factory','Latitude','Longitude'],[[r['Factory'],r['Latitude'],r['Longitude']] for r in coordinates],
        [280,112,112],caption='Table A1  Five supplied factory coordinates',numeric=(1,2))
    paper.table(['Division','Product name','Current assigned factory'],[[r['Division'],r['Product Name'],r['Factory']] for r in products],
        [68,288,148],caption='Table A2  Fifteen reference assignments  Origins are inferred from these static relationships')
    paper.save()


def executive(kpis):
    memo=Manuscript('executive_summary','Factory Reallocation and Shipping Optimization for Government Stakeholders',
                    'Executive summary | Independent educational analysis | 10 October 2026')
    memo.heading('Decision for stakeholder review')
    memo.paragraph('Support verification of logistics data and a narrowly scoped feasibility review before considering factory reassignment. The public educational sample identifies where further investigation is most useful, but it does not establish an operational business case, realized public benefits or a case for public investment.')
    memo.heading('What the sample establishes')
    memo.paragraph('The 2021-2024 sample has 10,194 records and 38,654 units, with sales of 141,783.63 and source gross profit of 93,442.80. Monetary units are unspecified; gross profit excludes freight and other operating costs. Chocolate represents 96.43% of demand. Geographic screening identifies five persistently distant product-region flows, comprising two Pacific and three Atlantic chocolate flows.')
    memo.paragraph('There are <b>zero validated historical lead-time records</b>. Every source interval is 2,000-2,011 days. Delivery times cannot be measured because delivery dates are absent. These failures prevent a verified performance or reassignment claim.')
    memo.heading('What the planning exercise suggests')
    memo.paragraph('At equal speed and profit priority, the assumption-based simulator flags Nutty Crunch Surprise, Fudge Mallows, Scrumdiddlyumptious, Milk Chocolate and Triple Dazzle Caramel for investigation at Secret Factory. These are hypothetical product-factory alternatives; none has historical outcome evidence or verified production constraints.')
    memo.table(['Planning indicator','Default result'],[
        ['Modeled dispatch allowance reduction','4.06%'],['Nonnegative joint contribution cases','54 of 81 cases or 66.67%'],
        ['Evidence readiness and verified coverage','0 of 100 and 0%'],['Products proposed for investigation','5 of 15 or 33.33%']],
        [340,164],caption='Planning indicators are not observed service improvements or outcome probabilities')
    memo.paragraph('The base modeled contribution change is +977.68 source monetary units over the mapped sample replay. Tested joint changes range from -4,090.69 to +4,066.00. No alternate assignment protects contribution in every sensitivity case. These figures are not annual savings, statistical confidence bounds or monetary benefits to government.')

    memo.new_page();memo.heading('Proposed next steps')
    memo.paragraph('<b>1  Establish reliable milestones.</b> Ask the data owner to verify order and ship dates, observed origin factories and delivery dates. Preserve the source records and document verified corrections. Retain Canadian demand in business totals and obtain destination coordinates for geographic comparisons.')
    memo.paragraph('<b>2  Review the most exposed flows.</b> Collect actual freight routes and tariffs for Milk Chocolate and Triple Dazzle Caramel in Pacific, and Nutty Crunch Surprise, Fudge Mallows and Scrumdiddlyumptious in Atlantic. The geographic screen highlights distance exposure; it does not show congestion, emissions or service failure.')
    memo.paragraph('<b>3  Verify production feasibility.</b> Obtain documented product compatibility, additional factory capacity over an agreed horizon, manufacturing differences, setup costs and transition requirements. The default proposals send 37,275 whole-product sample units to Secret Factory, compared with 884 units statically assigned there in the sample. Neither figure measures physical capacity; concentration makes verification essential.')
    memo.paragraph('<b>4  Evaluate a limited trial if evidence supports it.</b> Define eligible products and service requirements before any operational change. Compare observed dispatch and delivery performance and fully scoped costs with retained current assignments. An analyst should maintain the data/assumption audit, operating owners should validate capability and costs, and stakeholder reviewers should assess the measured evidence. These are proposed responsibilities, not existing commitments.')
    memo.heading('Conditions for a credible decision')
    memo.paragraph('A reassignment proposal should include validated shipment milestones, observed origin records, product-factory outcome evidence, capacity and capability checks, a complete transition-cost comparison, and independent evaluation on later observations. Report losses and service deterioration alongside gains. A positive planning score or clean software test does not establish a feasible or profitable move.')
    memo.paragraph('The sample contains no basis for estimating employment effects, emissions reductions, tax receipts, industry-wide congestion or public return on expenditure. Any such assessment requires separate evidence. No budget, plant-relocation incentive or infrastructure commitment is recommended from the current figures.')
    memo.heading('Delivery and evidence status')
    memo.paragraph('The completed project includes an auditable research paper, Streamlit simulator and risk panel, downloadable scenario results, source-data attribution and reproducible code. An independently extracted package reproduced its saved KPIs and passed 24 software tests. Account publication remains pending. This is an educational submission, not an official company study or government policy evaluation.')
    memo.paragraph('Evidence: datasets/cleaning_validation_summary.json; reports/eda/current_performance_report.md; reports/route_analysis/route_investigation_report.md; reports/recommendations/kpis.json and recommendation_report.md. The accompanying research paper supplies the full methods, metrics and limitations. Order sample: Maven Analytics US Candy Distributor; ZIP geography: SimpleMaps historical Basic snapshot, CC BY 4.0. All monetary figures use unspecified source units.','reference')
    memo.save()


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    kpis=load_json('reports/recommendations/kpis.json')
    clean=load_json('datasets/cleaning_validation_summary.json')
    assert clean['cleaned_rows']==10194 and clean['lead_time_training_rows']==0
    assert clean['cleaned_sales_total']=='141783.63' and clean['cleaned_gross_profit_total']=='93442.80'
    assert kpis['proposed_reassignments']==5 and abs(kpis['modeled_lead_time_reduction_pct']-4.061882247971285)<1e-8
    assert kpis['scenario_confidence_score']==0 and kpis['verified_recommendation_coverage_pct']==0
    assert not kpis['operational_recommendations_approved']
    queue=read_csv('reports/route_analysis/region_product_investigation_queue.csv')
    joint=read_csv('reports/recommendations/joint_portfolio_sensitivity.csv')
    assert len(joint)==81 and sum(float(row['Portfolio Contribution Change'])>=-1e-9 for row in joint)==54
    make_figures(queue,joint,kpis)
    research(read_csv('reports/eda/tables/factory_summary.csv'),read_csv('reports/eda/tables/region_summary.csv'),
        read_csv('reports/eda/tables/ship_mode_summary.csv'),read_csv('reports/model_comparison/diagnostic/model_metrics.csv'),
        queue,read_csv('reports/recommendations/selected_rows.csv'),kpis,read_csv('datasets/reference/products.csv'),
        read_csv('datasets/reference/factories.csv'))
    executive(kpis)
    print('Created research paper and executive summary PDFs with editable Markdown sources')


if __name__=='__main__':
    main()
