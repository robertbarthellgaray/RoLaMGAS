# ReachStar-informed resonance starters

Original RSS/Principia trajectory: **ReachStar on Bilibili**. The bundled
references are RoLaMGAS's date-adjusted JPL recreation, not an exact game replay.

`departure_seeds/reachstar_tour.json` contains twelve physical prefix records,
the full fifteen-event timing reference, an Earth-RTN departure direction, and
two Venus-return velocity-direction templates. Every prefix was recomputed and
independently solar-propagated before it was saved. Importable files are named
`departure_seeds/reachstar_imports/`. The corresponding plain search presets are
`examples/reachstar_*.json`.

Four additional `EVdvV` starters use fresh JPL dates in 2029, 2031, 2033 and 2039.
Their C3 values are about 18.03, 13.06, 10.16 and 13.89 km²/s² respectively;
modeled corrections range from 0.68 to 5.91 m/s. These are Venus-return starting
blocks, not completed outer-planet missions. The limited sampling did not find
a qualifying 2035 starter; that is not a proof that one does not exist.

Seven prefixes satisfy the ordinary Earth/Venus altitude floors. Five later
prefixes need the explicit research exceptions discussed in the study. Automatic
reuse re-evaluates the current C3, arrival speed, date windows, DSM budgets and
altitude floors; the stored pass flags and reference limits are not inherited.

For searches at other epochs, the historical/proposal initializer can use the
encounter durations and Earth-RTN direction. These are guesses only: copying a
1970 duration or direction to 2035 does not establish a working 2035 trajectory.

## Near-one-year Venus returns

A return after one planetary year is poorly conditioned as a center-to-center
Lambert problem: nearly coincident endpoints do not uniquely specify the useful
departure direction. A period-energy cone provides a shooting guess instead.

The new initializer operates only on an **explicitly requested `VdvV` leg**. It
sets a possible solar-period departure velocity, propagates toward a midpoint,
and leaves the normal solver to charge the resulting correction. No DSM is added
to a plain `VV` route. Both the incoming excess-speed sphere and heliocentric
orbital-period energy are respected by the starting velocity; flyby turning,
return location, correction cost and the next leg still require full validation.

Coherent branch combinations now include these Venus returns and two-revolution
Venus-to-Mercury transfers. The Mercury-to-Venus envelope admits the observed
approximately 41-day leg. Explicit user branch restrictions still take precedence.

Rebuild the physical reference files locally:

```powershell
.venv\Scripts\python.exe tools/build_reachstar_seeds.py --future
```

This uses the already cached historical JPL vectors. It makes no AI calls or
uploads. These source changes do not update an already installed executable;
they will be bundled in a future native build after local review.
