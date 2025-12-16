# Prompt: Transform Legal Text into OWL


## Objective
Convert the provided legal text into OWL for clarity and precision.


## Step by Step

1. Split the paragraph into sentences.
2. For each sentence identify the following relevant information:
- Subject: Entity (vehicle, person, etc.) that performs the action described in the conclusion.
- Conclusion: The action that is present in the main sentence.
- Deontic Modality: Optional. The importance of the action indicated in the conclusion. Either, should or must.
- Conditions: Things that have to be true, in order to the conclusion to be applicable.
3. Present the JSON with the extracted elements for each sentence.
4. For each JSON object with conclusion and conditions, *encode the OWL representation*.

- **Conclusion**:
* Predicate name is the deontic modality if it exists. If not explicit infer from the context and add a comment stating so.
* Arguments are the subject, action and specifications (if they exist). A specification can be a location, a time, a characteristic.

* Only create new classes or properties, if and only if, the existing ones *do not fit*.
* present the conclusion together with the corresponding added class or property.

- **Conditions**
* Find the subject, the verb, and the specification.
* Use the verb as the predicate name.
* The arguments are the subject and specifications.

5. *Build the rules* using the identified structure.
- If the subject is "you", replace the agent in the templates with the constant ego.

## Few Shot examples

### Example 1:

**Text:** You MUST stop behind the line at a junction with a 'Stop' sign and a solid white line across the road. Wait for a safe gap in the traffic before you move off.

**Step 1: Sentences**

1. You MUST stop behind the line at a junction with a 'Stop' sign and a solid white line across the road.
2. Wait for a safe gap in the traffic before you move off.

**Step 2: For each phrase, extract the relevant information**

1. You MUST stop behind the line at a junction with a 'Stop' sign and a solid white line across the road.

- Subject: "ego"
- Conclusion: "stop behind the line at a junction"
- Deontic modality: "must"
- Conditions:
* "the junction has a 'Stop' sign"
* "the junction has a solid white line across the road"

2. Wait for a safe gap in the traffic before you move off.

- Subject: "ego"
- Conclusion: "move off"
- Deontic modality: None
- Conditions:
* "there is a safe gap in the traffic"


**Step 3: Present the JSON**

```json
[
{
  "subject":"ego",
  "conclusion":"stop behind the line at a junction",
  "deontic_modality":"must",
  "conditions":[
    "the junction has a 'Stop' sign",
    "the junction has a solid white line across the road"
  ]
},
{
  "subject":"ego",
  "conclusion":"move off",
  "deontic_modality":null,
  "conditions":[
    "there is a safe gap in the traffic"
  ]
}
]
```

**Step 4: Identifying the properties**

```
:stopBehindLine rdf:type owl:DatatypeProperty ;
                rdfs:domain :VehicleAtJunctionWithStopAndSolidWhiteLine ;
                rdfs:range xsd:boolean .


:waitForSafeGap rdf:type owl:DatatypeProperty ;
                rdfs:domain :VehicleAtJunctionWithStopAndSolidWhiteLine ;
                rdfs:range xsd:boolean .
```

**Step 5: Build the rules**

```
:Vehicle rdf:type owl:Class.

:VehicleAtJunctionWithStopAndSolidWhiteLine rdf:type owl:Class;
  rdfs:subClassOf :Vehicle.

:VehicleAtJunctionWithStopAndSolidWhiteLineR171Compliant rdf:type owl:Class;
  rdfs:subClassOf :VehicleAtJunctionWithStopAndSolidWhiteLine.

:VehicleAtJunctionWithStopAndSolidWhiteLineR171CompliantDefault rdf:type owl:Class;
  owl:equivalentClass [
    owl:intersectionOf ( [
      rdf:type owl:Restriction;
      owl:onProperty :stopBehindLine;
      owl:hasValue "true"^^xsd:boolean;
    ] [
      rdf:type owl:Restriction;
      owl:onProperty :waitForSafeGap;
      owl:hasValue "true"^^xsd:boolean;
    ] );
    rdf:type owl:Class;
  ];
  rdfs:subClassOf :VehicleAtJunctionWithStopAndSolidWhiteLineR171Compliant.

:VehicleAtJunctionWithStopAndSolidWhiteLineR171CompliantMitigated rdf:type owl:Class;
  owl:equivalentClass [
    owl:intersectionOf ( [
      rdf:type owl:Class;
      owl:unionOf ( [
        rdf:type owl:Restriction;
        owl:onProperty :stopBehindLine;
        owl:hasValue "false"^^xsd:boolean;
      ] [
        rdf:type owl:Restriction;
        owl:onProperty :waitForSafeGap;
        owl:hasValue "false"^^xsd:boolean;
      ] );
    ] [
      rdf:type owl:Restriction;
      owl:onProperty :emergencyAbnormal;
      owl:hasValue "true"^^xsd:boolean;
    ] );
    rdf:type owl:Class;
  ];
  rdfs:subClassOf :VehicleAtJunctionWithStopAndSolidWhiteLineR171Compliant.

:VehicleAtJunctionWithStopAndSolidWhiteLineR171Violating rdf:type owl:Class;
  owl:equivalentClass [
    owl:intersectionOf ( [
      rdf:type owl:Class;
      owl:unionOf ( [
        rdf:type owl:Restriction;
        owl:onProperty :stopBehindLine;
        owl:hasValue "false"^^xsd:boolean;
      ] [
        rdf:type owl:Restriction;
        owl:onProperty :waitForSafeGap;
        owl:hasValue "false"^^xsd:boolean;
      ] );
    ] [
      rdf:type owl:Restriction;
      owl:onProperty :emergencyAbnormal;
      owl:hasValue "false"^^xsd:boolean;
    ] );
    rdf:type owl:Class;
  ];
  rdfs:subClassOf :VehicleAtJunctionWithStopAndSolidWhiteLine.
```

## Final Remarks

You task is to transform natural language text into OWL rules.
To do so, follow the Cheatsheet guide on how to write OWL, to fulfill the following steps:

1. Break the input into sentences.
2. For each sentence do the following relevant information:
3. Present the JSON with the extracted elements for each sentence.
4. For each JSON object with conclusion and conditions, identify the templates.