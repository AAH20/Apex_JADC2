# Apex JADC2 — Joint All-Domain Command and Control

F2T2EA kill chain, coalition federation, sovereign AI, NATO interoperability.

## Architecture

```mermaid
flowchart TD
    subgraph Sensors["Multi-Domain Sensors"]
        RADAR[Radar]
        EOIR[EO/IR]
        SAT[Satellite]
        CYBER[Cyber Sensors]
        EW[Electronic Warfare]
    end

    subgraph F2T2EA["F2T2EA Kill Chain"]
        FIND[Find\nMulti-Source Detection]
        FIX[Fix\nLocation Refinement]
        TRACK[Track\nMaintenance/Prediction]
        TARGET[Target\nPrioritization/Selection]
        ENGAGE[Engage\nWTA/Authorization]
        ASSESS[Assess\nBDA/Evaluation]
    end

    subgraph C2Layer["C2 Layer"]
        COP[Common Operational Picture]
        DM[Decision Support\nLatency Optimization]
        HITL[Human-in-the-Loop\nGovernance]
        ROE[ROE Compliance\nProportionality/Necessity]
        DECON[Deconfliction\nFratricide Prevention]
    end

    subgraph Federation["Coalition Federation"]
        NATO[NATO FMN\nInteroperability]
        MLS[Multi-Level Security\nCross-Domain]
        TAK[TAK/ATAK\nTactical Edge]
        LINK[Link 16/22\nData Links]
    end

    subgraph Sovereign["Sovereign AI"]
        AIRGAP[Air-Gapped\nDeployment]
        SC[Supply Chain\nAttestation]
        ZERO[Zero External\nDependencies]
    end

    subgraph WTA["Weapon-Target Assignment"]
        GWTA[Graph-Based WTA\nOptimization]
        DR[Dynamic Re-Assignment\nReal-Time]
        MO[Multi-Objective\nLethality/Survivability/Cost]
    end

    RADAR --> FIND
    EOIR --> FIND
    SAT --> FIND
    CYBER --> FIND
    EW --> FIND

    FIND --> FIX --> TRACK --> TARGET --> ENGAGE --> ASSESS
    ASSESS -->|Re-attack| FIND

    FIND --> COP
    FIX --> COP
    TRACK --> COP
    TARGET --> COP
    ENGAGE --> COP
    ASSESS --> COP

    COP --> DM
    DM --> HITL
    HITL --> ROE
    ROE --> DECON
    DECON --> ENGAGE

    NATO --> MLS
    MLS --> TAK
    TAK --> LINK

    AIRGAP --> SC
    SC --> ZERO

    TARGET --> GWTA
    GWTA --> DR
    DR --> MO
    MO --> ENGAGE
```

## F2T2EA Kill Chain Flow

```mermaid
sequenceDiagram
    participant S as Sensors
    participant F as Find
    participant Fx as Fix
    participant T as Track
    participant Tg as Target
    participant E as Engage
    participant A as Assess
    participant H as HITL

    S->>F: Multi-Source Detection
    F->>Fx: Contact Report
    Fx->>T: Track Initiation
    T->>Tg: Target Prioritization
    Tg->>H: Engagement Request
    H->>E: Authorization (ROE Check)
    E->>A: Engagement Execution
    A->>F: Battle Damage Assessment
    A->>H: Re-attack Recommendation
```

## WTA Optimization

```mermaid
flowchart TD
    TARGETS[Target List] --> GWTA[Graph-Based WTA]
    WEAPONS[Weapon List] --> GWTA
    GWTA --> OBJ{Multi-Objective\nOptimization}
    OBJ -->|Lethality| LETH[Lethality Score]
    OBJ -->|Survivability| SURV[Survivability Score]
    OBJ -->|Cost| COST[Cost Score]
    LETH --> ASSIGN[Weapon-Target Assignment]
    SURV --> ASSIGN
    COST --> ASSIGN
    ASSIGN --> DR{Dynamic\nRe-Assignment?}
    DR -->|Yes| GWTA
    DR -->|No| EXEC[Execute Engagement]
```

## Coalition Federation

```mermaid
flowchart TD
    subgraph NATO["NATO Federation"]
        FMN[FMN\nFederated Mission Network]
        MLS[Multi-Level Security\nClassification Levels]
        CDS[Cross-Domain Solution\nData Sharing]
    end

    subgraph Tactical["Tactical Edge"]
        TAK[TAK/ATAK\nTactical Devices]
        LINK16[Link 16\nAir/Surface]
        LINK22[Link 22\nTactical Data Link]
    end

    subgraph Sovereign["Sovereign AI"]
        AIRGAP[Air-Gapped\nDeployment]
        SC[Supply Chain\nAttestation]
        ZERO[Zero External\nDependencies]
    end

    FMN --> MLS
    MLS --> CDS
    CDS --> TAK
    TAK --> LINK16
    TAK --> LINK22

    AIRGAP --> SC
    SC --> ZERO
```

## Benchmark Comparisons

| Feature | Apex JADC2 | Palantir Gotham | Anduril Lattice | PTAH-OS-CJADC2 | God's Eye View |
|---------|-----------|-----------------|-----------------|-----------------|----------------|
| F2T2EA Kill Chain | ✅ Full | ✅ Partial | ✅ Partial | ✅ Full | ❌ |
| Coalition Federation | NATO FMN/MLS | ❌ | ❌ | ✅ | ❌ |
| Sovereign AI | Air-gapped/Zero deps | ❌ | ❌ | ❌ | ❌ |
| WTA | Graph-based optimization | ❌ | ❌ | ❌ | ❌ |
| ROE Compliance | Proportionality/Necessity | ❌ | ❌ | ❌ | ❌ |
| HITL Governance | ✅ | ✅ | ✅ | ❌ | ❌ |
| Open Source | AGPL-3.0 | ❌ | ❌ | ✅ | ✅ |
| NATO Interoperability | STANAG/MIP/NFFI | ❌ | ❌ | ❌ | ❌ |

## Tests

~372 tests, TDD-enforced.

## License

AGPL-3.0
