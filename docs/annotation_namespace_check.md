# Check a proposed BUB1B activator annotation

Public-source audit · 24 October 2026.

A 2026 nephrotoxicity paper's DGIdb-derived Table 3 assigns niflumic acid as a BUB1B activator and DIDS/3-phenyl-CPP as inhibitors. It supplies no BUBR1 functional experiment for those assignments. [Primary paper, Table 3](https://pmc.ncbi.nlm.nih.gov/articles/PMC13152955/)

The same drug trio appears under **ClC-Kb**, IUPHAR target **701**. IUPHAR lists BUBR1/BUB1B as target **1950**, while NCBI uses gene **701** for BUB1B. These are different identifier namespaces. [IUPHAR ClC family](https://www.guidetopharmacology.org/GRAC/FamilyDisplayForward?familyId=128), [IUPHAR Bub family](https://www.guidetopharmacology.org/GRAC/FamilyDisplayForward?familyId=559), [NCBI gene](https://www.ncbi.nlm.nih.gov/gene/701)

**Inference:** the matching numbers and drug sets strongly suggest a namespace-mapping error. We did not trace the ingestion code, so the error's exact origin is unproven. The annotation cannot establish that niflumic acid activates BUBR1. Primary niflumic-acid pharmacology measured chloride-channel currents rather than BUBR1 rescue. [Primary channel study](https://pubmed.ncbi.nlm.nih.gov/16244177/)

This finding excludes an unsupported target shortcut. It is not an efficacy comparison or a clinical safety judgment about niflumic acid.
