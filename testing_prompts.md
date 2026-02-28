# Testing Prompts

These are designed to probe specific capabilities and edge cases:

---

## Filter Generation Quality

* Show me all NBL patients who relapsed after age 3
* Females with AML at initial diagnosis in the IRS group III
* Patients with Wilms tumor who were under 2 years old
* ALL patients in standard risk group at end of first course of treatment
* RMS patients older than 10 years with stage M0 disease

---

## Anchor Pattern / Staging Disambiguation (should trigger clarification)

* Find patients with IRS group IV disease
* Show me M1 disease patients
* Patients with high risk INRG staging
* Stage 4 patients across all diseases

---

## Multi-field Combinations

* AML or ALL patients who are female and under 5 years
* NBL patients with very high risk INRG classification diagnosed before age 1
* Show me male WT patients older than 3 at diagnosis

---

## Edge Cases / Validator Stress

* Patients with tumor type AML (wrong field name — should trigger self-heal)
* Show me remission patients (vague — "remission" is not a field)
* All cancer patients (extremely broad — valid but retrieves everyone)

---

## General / Non-filter Queries

* What is PCDC?
* How are ages stored in the data?
* What diseases are available in the portal?

---

## Adversarial

* Show me `SELECT * FROM subjects` (SQL injection style — should generate GQL, not SQL)
* Generate a filter for the dataset with most patients (nonsensical — no such field)
* Patients where age is between 5 and 10 years (age in days — 1825 to 3650 — should enforce conversion)
