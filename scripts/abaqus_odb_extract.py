"""Read-only ODB extraction for Abaqus Python 2.7 and Python 3.

Adapted/reimplemented from jasonanewcoder/abaqus_skills/scripts/odb_extract.py
(MIT, copyright 2025 Abaqus Skills Library Contributors).
See references/upstream/LICENSE. JSON output; no CAE/GUI imports.
"""
from __future__ import print_function
import argparse
import json
import math
import sys


def number(value):
    result = float(value)
    if math.isnan(result) or math.isinf(result):
        raise ValueError('Non-finite ODB value')
    return result


def components(value):
    try:
        raw = value.data
    except Exception:
        raw = value.dataDouble
    try:
        return [number(x) for x in raw]
    except TypeError:
        return [number(raw)]


def location(value):
    result = {}
    instance = getattr(value, 'instance', None)
    result['instance'] = str(instance.name) if instance else None
    for key in ('nodeLabel', 'elementLabel', 'integrationPoint', 'position'):
        try:
            item = getattr(value, key)
            if item is None:
                continue
            result[key] = item if isinstance(item, (int, float)) else str(item)
        except Exception:
            pass
    return result


def field_max(field, field_key, metric='auto', component=None):
    labels = list(getattr(field, 'componentLabels', ()))
    if component is not None:
        if component in labels:
            index = labels.index(component)
        else:
            try:
                index = int(component)
            except (ValueError, TypeError):
                raise ValueError('Unknown component; available: ' + repr(labels))
        if index < 0 or index >= len(labels):
            raise ValueError('Component index out of range')
        metric = 'component_abs'
    elif metric == 'auto':
        kind = str(getattr(field, 'type', '')).upper()
        metric = 'mises' if field_key == 'S' and 'TENSOR' in kind else ('magnitude' if 'VECTOR' in kind else 'abs')
    best = None
    skipped = 0
    for value in field.values:
        data = components(value)
        if field_key.startswith('COPEN') and any(abs(x) >= 1e30 for x in data):
            skipped += 1
            continue
        if metric == 'mises':
            if 'MISES' not in [str(x).upper() for x in getattr(field, 'validInvariants', ())]:
                raise ValueError('MISES invariant unavailable for this field')
            signed = number(value.mises)
            score = signed
        elif metric == 'component_abs':
            signed = data[index]
            score = abs(signed)
        elif metric == 'magnitude':
            signed = math.sqrt(sum(x*x for x in data))
            score = signed
        elif metric == 'abs' and len(data) == 1:
            signed, score = data[0], abs(data[0])
        else:
            raise ValueError('Select a tensor invariant or component; tensor norm is not inferred')
        if best is None or score > best['value']:
            best = {'value': score, 'signed_value': signed, 'data': data, 'location': location(value)}
    if best is None:
        raise ValueError('No valid field values (undefined COPEN values excluded)')
    best.update(metric=metric, component=component, undefined_values_excluded=skipped)
    return best


def resolve_set(odb, name, instance=None):
    if instance:
        if instance not in odb.rootAssembly.instances:
            raise ValueError('Instance not found: ' + instance)
        roots = [(instance, odb.rootAssembly.instances[instance])]
    else:
        roots = [('ASSEMBLY', odb.rootAssembly)]
        roots += [(str(n), odb.rootAssembly.instances[n]) for n in odb.rootAssembly.instances.keys()]
    matches = []
    for owner, root in roots:
        for attr in ('nodeSets', 'elementSets'):
            repo = getattr(root, attr, {})
            for key in repo.keys():
                if str(key).lower() == name.lower():
                    matches.append((owner, attr, repo[key]))
        if matches and owner == 'ASSEMBLY':
            break  # Assembly sets take explicit precedence.
    if len(matches) != 1:
        raise ValueError('Set is absent or ambiguous; specify --instance. Matches: ' + repr([(x[0], x[1]) for x in matches]))
    return matches[0][2]


def history_data(step, variable, region=None):
    repos = step.historyRegions
    if region is None:
        choices = [str(k) for k in repos.keys() if variable in repos[k].historyOutputs]
        if len(choices) != 1:
            raise ValueError('Specify --region; matching histories: ' + repr(choices))
        region = choices[0]
    if region not in repos or variable not in repos[region].historyOutputs:
        raise ValueError('History region/variable not found')
    data = [[number(t), number(v)] for t, v in repos[region].historyOutputs[variable].data]
    if not data:
        raise ValueError('History is empty')
    return {'region': region, 'variable': variable, 'data': data, 'last': data[-1]}


def energies(step):
    choices = [k for k in step.historyRegions.keys() if str(k).lower().startswith('assembly')
               and 'ALLIE' in step.historyRegions[k].historyOutputs]
    if len(choices) != 1:
        raise ValueError('Unique assembly energy history unavailable; request ALLIE/ALLSD/ALLKE etc.')
    key = choices[0]
    outputs = step.historyRegions[key].historyOutputs
    data = {}
    for variable in ('ALLIE', 'ALLSE', 'ALLKE', 'ALLAE', 'ALLSD', 'ALLVD', 'ALLFD', 'ALLPD', 'ALLWK', 'ETOTAL'):
        if variable in outputs and len(outputs[variable].data):
            data[variable] = [[number(t), number(v)] for t, v in outputs[variable].data]
    ratios = {}
    ie_by_time = dict(data['ALLIE'])
    for variable in ('ALLKE', 'ALLAE', 'ALLSD', 'ALLVD'):
        valid, undefined = [], 0
        for t, v in data.get(variable, []):
            denominator = ie_by_time.get(t)
            if denominator is None or abs(denominator) <= 1e-30:
                undefined += 1
            else:
                valid.append([t, abs(v / denominator)])
        ratios[variable + '/ALLIE'] = {'max': max([x[1] for x in valid]) if valid else None,
                                     'last_valid': valid[-1] if valid else None,
                                     'undefined_count': undefined}
    return {'region': str(key), 'histories': data, 'ratios': ratios,
            'note': 'Ratios are diagnostics, not universal acceptance thresholds. Inspect the complete loading history.'}


def extract(odb, args):
    names = list(odb.steps.keys())
    if not names:
        raise ValueError('ODB has no analysis steps')
    name = args.step or names[-1]
    if name not in odb.steps:
        raise ValueError('Step not found: ' + name)
    step = odb.steps[name]
    if not len(step.frames):
        raise ValueError('Step has no frames')
    frame = step.frames[-1]
    positive = any(number(f.frameValue) > 0 for f in step.frames)
    result = {'step': str(name), 'frame_count': len(step.frames), 'final_frame_time': number(frame.frameValue),
              'positive_time_frame': positive, 'solver_completion_verified': False,
              'completion_note': 'Confirm completion in .sta/.msg/.log; an ODB/frame alone is insufficient.'}
    if not positive and not args.allow_initial:
        raise ValueError('Only initial frames exist; use --allow-initial for initialization diagnostics')
    if args.field:
        if args.field not in frame.fieldOutputs:
            raise ValueError('Field not found: ' + args.field)
        field = frame.fieldOutputs[args.field]
        if args.set_name:
            field = field.getSubset(region=resolve_set(odb, args.set_name, args.instance))
        if args.sum:
            if args.field not in ('RF', 'RM', 'CF') or not args.set_name:
                raise ValueError('--sum requires a set and RF/RM/CF; arbitrary field sums are not meaningful')
            if str(getattr(field, 'type', '')).upper() != 'VECTOR':
                raise ValueError('Expected a vector force/moment field')
            total = None
            for value in field.values:
                row = components(value)
                if total is None:
                    total = [0.] * len(row)
                total = [x+y for x, y in zip(total, row)]
            if total is None:
                raise ValueError('Selected set contains no field values')
            result['field_sum'] = total
        else:
            result['field_max'] = field_max(field, args.field, args.metric, args.component)
    if args.history:
        result['history'] = history_data(step, args.history, args.region)
    if args.energy:
        result['energy'] = energies(step)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('odb')
    p.add_argument('--step')
    p.add_argument('--field')
    p.add_argument('--metric', choices=('auto', 'magnitude', 'mises', 'abs'), default='auto')
    p.add_argument('--component', help='Component label or zero-based index')
    p.add_argument('--set', dest='set_name')
    p.add_argument('--instance')
    p.add_argument('--sum', action='store_true')
    p.add_argument('--history')
    p.add_argument('--region')
    p.add_argument('--energy', action='store_true')
    p.add_argument('--allow-initial', action='store_true')
    a = p.parse_args(argv)
    if a.instance and not a.set_name:
        p.error('--instance requires --set')
    if a.sum and not a.field:
        p.error('--sum requires --field')
    odb = None
    try:
        from odbAccess import openOdb
        odb = openOdb(path=a.odb, readOnly=True)
        result = extract(odb, a)
        result['ok'] = True  # Extraction only; solver_completion_verified remains separate.
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except Exception as e:
        print('ERROR: ' + str(e), file=sys.stderr)
        print(json.dumps({'ok': False, 'error': str(e), 'error_type': type(e).__name__}))
        return 1
    finally:
        if odb is not None:
            odb.close()


if __name__ == '__main__':
    sys.exit(main())
