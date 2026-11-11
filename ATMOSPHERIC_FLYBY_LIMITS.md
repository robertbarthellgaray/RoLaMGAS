# Low-altitude flyby screening

An altitude floor is an analyst screening assumption, not proof of atmospheric
survivability. Neither Earth nor Venus has a sharp boundary above which drag and
heating are exactly zero. The point-mass flyby solver does not model either effect.

The ReachStar reconstruction's last Earth encounter has V-infinity about
17.358 km/s. Using the Earth GM and equatorial radius in the solver:

| Periapsis altitude | Maximum unpowered turn | Periapsis speed |
|---|---:|---:|
| 134 km | 19.4423 degrees | 20.5841 km/s |
| 200 km | 19.2783 degrees | 20.5543 km/s |
| 300 km | 19.0351 degrees | 20.5101 km/s |

Lowering the pass from 200 to 134 km gains about 0.164 degrees of turn. At this
V-infinity, that is about 49.7 m/s difference between the limiting outgoing
velocity vectors. It can matter to a marginal itinerary; it cannot explain a
multi-km/s mismatch. These values describe ideal gravity only.

There is no universal minimum safe altitude without spacecraft properties and
atmospheric conditions. Drag acceleration scales as rho*v_rel^2/(2*beta), where
beta=m/(Cd*A). Small total speed loss does not establish acceptable local heating,
solar-array temperature, material erosion, structural loads or attitude control.
Thermal modeling must use an appropriate rarefied-flow treatment where applicable.

An Earth assessment needs a suitable upper-atmosphere model, encounter location
and time, solar/geomagnetic conditions, atmospheric rotation/winds, spacecraft
mass, exposed area, attitude and thermal properties. Density varies with solar
and geomagnetic activity. A single short pass is different from a repeated low
orbit, but cannot simply be assumed lossless.

Venus Express survived experimental passes around 130–135 km, but these were
deliberate aerobraking passes with thermal and operational precautions. They do
not demonstrate negligible drag at those altitudes or safe passage for another
spacecraft at a different excess speed. Equal numerical altitudes above Earth
and Venus are not equivalent atmospheric environments.

RoLaMGAS retains its usual screening floors. Lower-altitude research results
must disclose their assumptions, and require separate drag/heating evaluation.
RSS/Principia's n-body treatment alone does not establish what atmospheric model,
vehicle configuration or heating settings were used in the source game flight.

Sources:

- [NOAA: satellite drag and upper-atmosphere variability](https://www.spaceweather.gov/impacts/satellite-drag)
- [ESA: Venus Express rises again](https://www.esa.int/Science_Exploration/Space_Science/Venus_Express/Venus_Express_rises_again)
- [ESA: Venus Express thermal management during aerobraking](https://blogs.esa.int/rocketscience/2014/06/30/hotter-and-hotter/)
- [NASA/NOAA: U.S. Standard Atmosphere 1976](https://ntrs.nasa.gov/citations/19770009539)
