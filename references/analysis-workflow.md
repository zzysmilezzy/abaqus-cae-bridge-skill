# Analysis workflow and evidence

## Execution modes and compatibility

Use the existing main-thread bridge for open-model work. Inspect existing INP/log/ODB files offline without a GUI connection. For a new headless task, when requested, use an isolated directory and unique model/job names with `abaqus cae noGUI=model_setup.py`. Do not replace an open model with a new `Mdb()` or overwrite a database merely because a reference does so. Check the INP first; the static checker is not an Abaqus datacheck.

The checker resolves relative include files against one job-submission directory (default: main INP parent). Supply `--include-base` if the actual submission directory differs. Quoted labels preserve case/spaces; unquoted labels are normalized. These rules follow [Abaqus Input Syntax Rules](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEMODRefMap/simamod-c-inputsyntax.htm); keyword abbreviations/parameter expansion remain outside this heuristic checker.

Check the actual Python/API version. Local Abaqus 2021 uses Python 2.7; system Python uses 3. The new unit and ODB tools support both. The diagnostics tool requires system Python 3. Reference templates are examples, not prevalidated APIs; inspect syntax, signatures and compiler compatibility before use. In a persistent bridge namespace, Abaqus/numpy imports can shadow builtins: use an explicit builtins module for reductions where needed.

For subroutines, match the exact Standard/Explicit and release interface, verify the supported compiler/toolchain, then run a minimal or single-element test before a full model. Third-party files labeled `official` are not independently verified provenance.

## Inputs and run plan

Separate observed model facts, confirmed inputs and assumptions. Confirm conclusion-changing units, supports, load history, contact gaps/friction and bolt force versus fixed-length holding. Do input-independent checks while awaiting answers. Never silently use example dimensions, Q235, load or density defaults. Abaqus has no built-in units; the conversion helper explicitly targets N-mm-s-tonne, not all models.

Inspect actual initial gaps/adjustments, normals/curvature, face selection, Tie coverage and contact/Tie/Coupling intersections before tuning contact algorithms. CAD equality need not mean equal faceted surfaces. Warning counts alone do not prove disconnected geometry or an invalid constraint. Read actual regions and overconstraint chains.

Estimate equations, CPU/RAM/scratch and runtime against the user's constraints. Avoid overlapping large jobs. Use unique run directories/names to prevent stale logs being treated as current evidence.

## Diagnosis and controlled experiments

| Evidence | First checks |
|---|---|
| Preprocessor/keyword error | Actual release/API, names, syntax, includes and external data |
| First increment repeatedly fails with SDIs | Initial contact geometry/adjustments, load/support sequence, active-set changes, constraint intersections |
| Zero pivot / singularity | Free modes, disconnected parts, repeated constraints; print chains where appropriate |
| Negative eigenvalues | Instability, softening, contact and constraints; not automatically material failure |
| Distortion | Mesh/element formulation, geometry/units, load direction and physical plausibility |
| CAE remains SUBMITTED / interactive messaging fails | Solver files, real process state and ODB frames; messaging failure alone is not solver failure |

Before each rerun record the hypothesis, changed parameter group and decisive check. If a small planned group repeats the same failure without improvement, summarize the evidence and obtain a more discriminating diagnostic before expanding variants. Do not accumulate blind parameter trials. Smaller increments cannot repair incorrect supports/regions/constraints.

Penalty, stabilization, tracking and line search are numerical experiments. If helpful, inspect penetration, actual slip relative to mesh/curvature, damping force/energy and parameter sensitivity. Small sliding is justified by interface relative motion, not actuator displacement alone. Do not silently change friction, physical gaps, force/length holding, materials or analysis type to obtain a pass. Dynamics used as quasi-static regularization needs confirmed density/time conventions and inertial checks throughout loading and at the end.

## Completion and verification

1. Check `.sta/.msg/.dat/.log` completion/abort/termination evidence and timestamps. A missing lock, existing ODB or CAE SUBMITTED state proves neither success nor liveness. A sender timeout does not cancel a solver or command; inspect before resubmitting.
2. Verify every requested step reached its intended end with positive-time converged frames, correct final displacement and preload state. Distinguish a completed preload from the complete task. Initial-only ODBs are not solved states.
3. Check reaction/load and moment balance, units and deformed shape. Maximum RF is not total reaction. Avoid summing nodal displacements or integration-point stresses as a physical resultant.
4. Inspect stress/plasticity/contact gap/pressure/slip in their regions. Undefined COPEN sentinels are missing data; count and exclude them. Review initial node movement magnitudes.
5. Inspect complete energy histories: ALLKE, ALLAE, ALLSD and ALLVD relative to ALLIE are useful diagnostics, with context-dependent limits. Near-zero denominators are undefined. A small final ratio can hide earlier contamination; generic 1%/5% thresholds are not universal acceptance criteria.
6. Use relevant benchmarks, mesh/increment and numerical-parameter sensitivity when they affect the conclusion. Report checks not performed. Software fixture tests are not finite-element validation.

Deliver the actual accepted model/input, run path, changes and limitations. Keep failed variants distinguishable. Distinguish unsaved CAE copies from saved INP/ODB files. Apply project research-archive instructions.

On cancellation, stop only the identified task-owned solver and verify its end, then stop the bridge. `--stop` stops the bridge, not an analysis. Do not kill CAE/unrelated jobs or reconnect/resume cancelled work unless requested.
