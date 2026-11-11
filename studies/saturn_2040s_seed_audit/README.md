# Saturn 2040s search and reference-seed audit

The requested target is Saturn with launch C3 below 20 km²/s² and flight time
below ten years, launching in 2040–2049. No passing candidate was found in the
checks below. These restricted searches do not establish infeasibility.

## Unpowered root-tree survey

`tools/search_fast_saturn.py` solves scalar roots for matching incoming and
outgoing hyperbolic excess speeds and checks the available flyby turn angles.
The sequences are EVVEJS and EVEEJS. This survey used the first of each month
in 2040–2049 at C3 12.5 and 18.5: 240 launch-month/energy combinations. It uses
the locally cached JPL state vectors. The limits were 19.99999 km²/s² and
9.99999 years, arrival V-infinity at most 12 km/s, and minimum altitudes of
300 km at Venus, 200 km at Earth, and 10,000 km at Jupiter. There are no DSMs
or powered flybys in this survey.

All 240 combinations completed; none passed. [trials.tsv](trials.tsv) contains
the number of departure roots and intermediate chains constructed for each
combination. A trial is a root-tree traversal, not a single Lambert solve.
Launch days between the monthly samples, other C3 values, other branches or
routes, and trajectories requiring DSMs remain untested by this survey.

Repeat from the project directory:

```powershell
python tools/search_fast_saturn.py --monthly --start-year 2040 --end-year 2049 --c3 12.5 --c3 18.5 --max-c3 19.99999 --max-years 9.99999 --workers 2 --cache "$env:LOCALAPPDATA\RoLaMGAS\cache" --output .build/saturn_2040s_c3_20
```

The output checkpoints now include their C3 and flight-time limits. Reusing an
output directory with changed limits recalculates the affected trials instead
of silently reusing incompatible results.

## Reference initialization fixes

The audit identified three restrictions in the app's search:

- It selected only the first three matching historical/proposal references.
- A retained reference was not guaranteed an optimizer start if the branch's
  full-refinement slots were occupied by other initial guesses.
- It projected even an already in-range reference departure onto the selected
  C3 boundary, changing the encounter schedule unnecessarily.

The updated search attempts every matching reference, preserves the first leg
when its C3 is already permitted, and gives each retained reference its own
feasibility refinement of up to 60 iterations, capped by the user's configured
iteration limit. Refined references then compete for the normal full-refinement
slots. Checkpoints report eligible, attempted, C3-rejected, duplicate, retained,
refinement-attempted, evaluated and passing counts, plus reference names.
Random initial guesses still use the selected C3 boundary and all evaluated
complete trajectories must satisfy the hard C3 range.

A limited real-JPL smoke test covered 20 branch jobs across Saturn EVEEJS,
EVEVES and EVEdvES, and Jupiter EVEEJ and EVVEJ. It attempted 200 reference
initializations and retained 119; all 119 received a refinement attempt.
No passing candidate was produced in this small check. It verifies expanded
coverage, not a demonstrated improvement in the number of passing solutions.
The source timings remain initial guesses: they are not validated full-chain
solutions retargeted to the planetary phases of the 2040s. The catalog also
does not contain a numerical seed extracted from every collected report PDF.
