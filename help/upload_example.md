I upload a spreadsheet of city contracts. First I connect `department` with `contract number`, related by `contract_type`.

    source: city_department  
    target: contract_number  
    relationship: contract_type (selected from dropdown)

Then I connect `contract number` to `company` and I type "city contract" in `Related by`  

    source: contract_number 
    target: company
    relationship: "city contract" (typed in the box)

Then I click "Build Graph" and it generates a network graph of city departments, connecting to contract numbers, connecting to companies. 