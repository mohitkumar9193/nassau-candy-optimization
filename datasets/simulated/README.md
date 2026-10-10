# Simulated inputs for scenario exploration

`logistics_assumptions.json` contains explicitly hypothetical inputs introduced for the scenario simulator. It does not modify historical orders, dates, reference coordinates or product assignments. Every numeric logistics/dispatch parameter is assumed, not measured or calibrated.

The simulation replays the historical sample's mapped demand at each factory. It is not a demand forecast. Equal factory preparation times and neutral manufacturing multipliers provide a comparison starting point; they do not establish production compatibility, capacity, costs or historical performance. Unknown capacity and compatibility remain null.

Money uses source monetary units because the dataset dictionary does not specify currency. The assumed reassignment cost is charged once per product-factory scenario, over the full sample replay. Outputs cover only mapped orders, and charge the entire assumed setup cost to that subset; they cannot be extrapolated to unmapped Canadian demand without additional inputs.

The modeled lead time is an assumed order-to-dispatch preparation allowance plus an explicit distance-related dispatch-coordination buffer. It is not measured shipment lead time, travel time, or delivery time. Distance divided by vehicle speed is deliberately not used to represent order-to-shipment time.

Sensitivity grids vary assumptions jointly. Their bounds are scenarios, not confidence intervals or probabilities. Before real implementation, verify actual dates, factory-product outcome history, freight tariffs, factory preparation times, costs, capacity and compatibility.
