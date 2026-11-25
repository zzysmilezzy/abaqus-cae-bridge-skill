"""Convert SI <-> N-mm-s-tonne units; never infer the model's unit system.

Inspired by jasonanewcoder/abaqus_skills (MIT); see references/upstream/LICENSE.
Runs on system Python 3 and Abaqus Python 2.7. No Abaqus import or side effects.
"""
from __future__ import print_function
import argparse
import json
import math

# (N-mm-s-tonne unit, SI unit, SI-to-local multiplier)
QUANTITIES = {
    'length': ('mm', 'm', 1e3),
    'force': ('N', 'N', 1.0),
    'mass': ('tonne', 'kg', 1e-3),
    'stress': ('MPa', 'Pa', 1e-6),
    'elastic_modulus': ('MPa', 'Pa', 1e-6),
    'density': ('tonne/mm^3', 'kg/m^3', 1e-12),
    'velocity': ('mm/s', 'm/s', 1e3),
    'acceleration': ('mm/s^2', 'm/s^2', 1e3),
    'specific_heat': ('N*mm/(tonne*K)', 'J/(kg*K)', 1e6),
    'thermal_conductivity': ('mW/(mm*K)', 'W/(m*K)', 1.0),
    'convection': ('mW/(mm^2*K)', 'W/(m^2*K)', 1e-3),
    'heat_flux': ('mW/mm^2', 'W/m^2', 1e-3),
    'heat_generation': ('mW/mm^3', 'W/m^3', 1e-6),
    'energy': ('N*mm', 'J', 1e3),
    'power': ('mW', 'W', 1e3),
    'latent_heat': ('N*mm/tonne', 'J/kg', 1e6),
}


def convert(quantity, value, direction):
    local, si, factor = QUANTITIES[quantity]
    if math.isnan(value) or math.isinf(value):
        raise ValueError('Value must be finite')
    if direction == 'to-local':
        result, source_unit, target_unit = value * factor, si, local
    else:
        result, source_unit, target_unit = value / factor, local, si
    return {'quantity': quantity, 'input': value, 'input_unit': source_unit,
            'value': result, 'unit': target_unit, 'system': 'N-mm-s-tonne'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('direction', choices=('to-local', 'to-si'))
    p.add_argument('quantity', choices=sorted(QUANTITIES))
    p.add_argument('value', type=float)
    a = p.parse_args(argv)
    try:
        print(json.dumps(convert(a.quantity, a.value, a.direction), allow_nan=False))
    except ValueError as e:
        p.error(str(e))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
