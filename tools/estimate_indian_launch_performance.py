"""Reproduce an explicitly approximate LVM3 C3 curve from NSIL's 2025 plot.

Requires numpy/scipy; matplotlib only for --plot. No network access.
The digitized observations are historical source readings, not flight guarantees.
"""
import argparse
import csv
import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / 'studies/international_launch_performance'
MU, RE, HP = 398600.4418, 6378.137, 170.0
# Visually checked samples from page 5, blue 170 km perigee curve.
# Plot resolution warrants ~50 kg reading uncertainty, not single-kg precision.
OBSERVATIONS = [(20000, 5050), (30000, 4400), (40000, 3950),
                (60000, 3550), (80000, 3250), (100000, 3100),
                (150000, 2950), (200000, 2800), (300000, 2700),
                (400000, 2650)]
SOURCE = ('https://web.archive.org/web/20251113162900/https://www.nsilindia.co.in/'
          'sites/default/files/NSIL%20Launch%20Requistion%20opportunity.pdf')


def speed(c3):
    return np.sqrt(2 * MU / (RE + HP) + np.asarray(c3))


def fit_stage(c3, masses, propellant=28000., exhaust_speed=4.334):
    """Effective ignition-velocity offset and inert mass, not an ascent model."""
    velocity = speed(c3)
    result = least_squares(
        lambda x: x[0] + exhaust_speed * np.log1p(propellant / (x[1] + masses)) - velocity,
        [4., 4300.], bounds=([-30., 0.], [30., 100000.]),
        xtol=1e-12, ftol=1e-12, gtol=1e-12)
    if not result.success:
        raise RuntimeError(result.message)
    offset, inert_mass = result.x

    def predict(query):
        return propellant / np.expm1((speed(query) - offset) / exhaust_speed) - inert_mass

    return predict, dict(effective_velocity_offset_km_s=float(offset),
                         fitted_effective_inert_mass_kg=float(inert_mass),
                         assumed_propellant_kg=propellant,
                         assumed_effective_exhaust_speed_km_s=exhaust_speed)


def build(plot=False):
    apogee, mass = np.array(OBSERVATIONS, dtype=float).T
    c3 = -2 * MU / (2 * RE + HP + apogee)
    # Fit only the near-escape portion; keep the more distant observations for review.
    near = apogee >= 60000
    prediction, parameters = fit_stage(c3[near], mass[near])
    query = np.arange(0., 31., 1.)
    capacities = prediction(query)
    if not (np.all(np.isfinite(capacities)) and np.all(capacities > 0)
            and np.all(np.diff(capacities) < 0)):
        raise ValueError('Invalid capacity curve')

    # An alternative local exponential model tests model-form sensitivity.
    vv = speed(c3[near]); mm = mass[near]; vref = vv[0]
    alt = least_squares(lambda x: x[0] * np.exp(-(vv-vref)/4.334) - x[1] - mm,
                        [mm[0]+6000, 6000], bounds=([0., 0.], [1e6, 1e6]))
    alternative = alt.x[0] * np.exp(-(speed(query)-vref)/4.334) - alt.x[1]
    # Hold out alternating calibration points to test interpolation, not extrapolation.
    hold = np.arange(len(mm)) % 2 == 1
    check, _ = fit_stage(c3[near][~hold], mm[~hold])
    residual = check(c3[near][hold])-mm[hold]
    row = dict(
        international_id='nsil2025_lvm3_estimate',
        vehicle='LVM3 · NSIL-based estimate',
        source_label='Estimated from NSIL curves · 2025', source_url=SOURCE,
        data_kind='calibrated_stage_estimate', source_year=2025,
        launch_site='SDSC-SHAR · source launch azimuth 107°',
        fairing='5 m (source brochure)', adapter='Mass accounting unspecified',
        display_rounding_kg=100, valid_c3_range=[0., 30.],
        query_grid_c3=query.tolist(), points=np.column_stack([query, capacities]).tolist(),
        ground_rules=(
            'RoLaMGAS model estimate, not published positive-C3 performance or a provider guarantee. '
            'Calibrated to approximate readings of NSIL November 2025 brochure p.5, '
            '170 km perigee, launch azimuth 107°, argument of perigee 178°. '
            'All source points have negative C3; 0–30 km²/s² is extrapolated. '
            'Effective upper-stage model assumes 28 t propellant and 4.334 km/s exhaust speed; '
            'velocity offset and effective inert mass are fitted, not measured. '
            'Brochure configuration upgrades, reserves, adapters, declination and ascent losses '
            'are not independently resolved. Rounded to 100 kg; uncertainty grows with C3. '
            'Do not use as a hard feasibility or payload guarantee. No extension beyond C3=30.'),
        model_parameters=parameters,
        source_c3_range=[float(c3.min()), float(c3.max())],
        calibration_c3_range=[float(c3[near].min()), float(c3[near].max())])
    report = dict(
        vehicle=row,
        source_samples=[dict(apogee_altitude_km=float(a), perigee_altitude_km=HP,
                             c3_km2_s2=float(c), approximate_payload_kg=float(m))
                        for a,c,m in zip(apogee,c3,mass)],
        calibration_rms_kg=float(np.sqrt(np.mean((prediction(c3[near])-mm)**2))),
        alternating_holdout_rms_kg=float(np.sqrt(np.mean(residual**2))),
        sensitivity_note='Alternative model spread is not a confidence interval; actual error may be larger.',
        alternative_exponential_points=np.column_stack([query,alternative]).tolist())
    (STUDY/'indian_lv_nsil_2025_model.json').write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False)+'\n', encoding='utf-8')
    with (STUDY/'indian_lv_nsil_2025_estimates.csv').open('w',newline='',encoding='utf-8') as stream:
        writer=csv.writer(stream)
        writer.writerow(['C3_km2_s2','estimated_payload_kg_rounded_100kg','alternative_model_kg_rounded_100kg'])
        writer.writerows((int(c),int(round(m/100)*100),int(round(a/100)*100))
                         for c,m,a in zip(query,capacities,alternative) if c%5==0)
    if plot:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig, ax=plt.subplots(figsize=(10,6))
        ax.scatter(c3,mass,label='Approximate NSIL plot readings (170 km perigee)',color='#2677a5')
        x=np.linspace(c3.min(),30,400)
        ax.plot(x,prediction(x),'--',label='Calibrated effective-stage model',color='#b45e23')
        ax.plot(query,alternative,':',label='Alternative local model (sensitivity check)',color='#777777')
        ax.axvline(0,color='gray',lw=1)
        ax.axvspan(0,30,color='#b45e23',alpha=.07,label='Extrapolated; not provider-rated')
        ax.set(xlabel='Earth departure C3 (km²/s²)',ylabel='Estimated payload (kg)',
               title='LVM3: NSIL-based engineering estimate',ylim=(0,None))
        ax.grid(alpha=.2);ax.legend(fontsize=8)
        fig.text(.5,.02,'2025 brochure, p.5 · Model assumptions and source configuration matter · No confidence interval implied',ha='center',fontsize=8)
        fig.tight_layout(rect=(0,.05,1,1))
        fig.savefig(STUDY/'indian_lv_nsil_2025_model.png',dpi=160)
        plt.close(fig)
    print(json.dumps(dict(parameters=parameters,calibration_rms_kg=report['calibration_rms_kg'],
                          holdout_rms_kg=report['alternating_holdout_rms_kg'],
                          estimates={str(int(c)):int(round(m/100)*100) for c,m in zip(query,capacities) if c%5==0}),indent=2))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plot',action='store_true')
    build(parser.parse_args().plot)
