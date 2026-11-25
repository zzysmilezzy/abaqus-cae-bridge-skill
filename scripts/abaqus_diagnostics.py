"""Offline, read-only INP checks and solver-file evidence (system Python 3).

Ideas adapted from jasonanewcoder/abaqus_skills (MIT), with scoped label checks,
recursive includes, explicit unit assumptions, and conservative job status.
Does not connect to CAE, submit/terminate jobs, or edit model files.
"""
import argparse
from collections import deque
import json
import re
from pathlib import Path


def tokens(line):
    return [x.strip() for x in re.split(r',(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)', line)]


def keyword(line):
    fields = tokens(line[1:])
    params = {}
    quoted = []
    for item in fields[1:]:
        pair = item.split('=', 1)
        key = pair[0].strip().lower()
        value = pair[1].strip() if len(pair) == 2 else True
        if isinstance(value, str) and value.startswith('"') and value.endswith('"'):
            quoted.append(key)
            value = value[1:-1]
        params[key] = value
    params['__quoted__'] = quoted
    return fields[0].lower(), params


def label_name(params, key):
    value = str(params.get(key, ''))
    return value if key in params.get('__quoted__', ()) else ''.join(value.split()).upper()


def read_text(path):
    raw = path.read_bytes()
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    return raw.decode('utf-8', errors='replace')


def inp_check(path, units=None, include_base=None):
    errors, warnings, sections, files = [], [], [], []
    incomplete = False
    run_dir = Path(include_base).resolve() if include_base else Path(path).resolve().parent

    def walk(current, stack):
        nonlocal incomplete
        current = current.resolve()
        if current in stack:
            errors.append({'file': str(current), 'message': 'Cyclic *Include'})
            incomplete = True
            return
        if not current.is_file():
            errors.append({'file': str(current), 'message': 'Input/include file missing'})
            incomplete = True
            return
        files.append(str(current))
        lines = deque(enumerate(read_text(current).splitlines(), 1))
        while lines:
            number, line = lines.popleft()
            text = line.strip()
            if not text or text.startswith('**'):
                continue
            if text.startswith('*'):
                while text.endswith(','):
                    following = lines.popleft() if lines else None
                    if following is None:
                        break
                    n, more = following
                    if more.strip().startswith('**') or not more.strip():
                        continue
                    if more.lstrip().startswith('*'):
                        # New keyword, not a continuation. Process it next.
                        lines.appendleft((n, more))
                        break
                    text += more.strip()
                kw, params = keyword(text)
                if kw == 'include':
                    child = params.get('input')
                    if not child:
                        errors.append({'file': str(current), 'line': number,
                                       'message': '*Include has no INPUT'})
                        incomplete = True
                    else:
                        if 'input' not in params['__quoted__']:
                            child = ''.join(child.split())
                        walk(run_dir / child, stack + [current])
                else:
                    sections.append({'kw': kw, 'params': params, 'file': str(current),
                                     'line': number, 'body': []})
            elif sections:
                sections[-1]['body'].append((number, text))

    walk(Path(path), [])
    step = None
    step_count = 0
    scope = ('model', '')
    seen = {}
    materials, used = set(), []
    for s in sections:
        kw, params = s['kw'], s['params']
        where = {'file': s['file'], 'line': s['line']}
        if kw == 'part':
            scope = ('part', label_name(params, 'name'))
        elif kw == 'instance':
            scope = ('instance', label_name(params, 'name'))
        elif kw in ('end part', 'end instance'):
            scope = ('model', '')
        if kw == 'step':
            step_count += 1
            if step is not None:
                errors.append(dict(where, message='Nested *Step; preceding step is unclosed'))
            step = s
        elif kw == 'end step':
            if step is None:
                errors.append(dict(where, message='*End Step without *Step'))
            step = None
        if kw == 'material' and params.get('name'):
            materials.add(label_name(params, 'name'))
        if kw.endswith('section') and params.get('material'):
            used.append((label_name(params, 'material'), where))
        if kw in ('node', 'element') and not (kw == 'node' and 'input' in params):
            match = re.match(r'(?:C3D|CPE|CPS|CAX|M3D|S)(\d+)', str(params.get('type', '')).upper())
            expected = int(match.group(1)) if match else {'CONN3D2': 2, 'B31': 2, 'B32': 3, 'T3D2': 2}.get(str(params.get('type', '')).upper())
            pending = 0
            for number, row in s['body']:
                entries = [x.strip() for x in row.split(',') if x.strip()]
                if kw == 'element':
                    if expected is None:
                        continue  # Unknown connectivity layout: no duplicate-label claim.
                    if pending:
                        pending = max(0, pending - len(entries))
                        continue
                    pending = max(0, expected - (len(entries) - 1))
                label = row.split(',')[0].strip()
                if not label.isdigit():  # Element connectivity continuation is not a definition.
                    continue
                key = (scope, kw, int(label))
                if key in seen:
                    errors.append({'file': s['file'], 'line': number,
                                   'message': 'Duplicate %s label %s in %s' % (kw, label, scope)})
                seen[key] = (s['file'], number)
        if units == 'N-mm-s-tonne' and kw in ('density', 'elastic') and s['body']:
            try:
                value = float(s['body'][0][1].split(',')[0].replace('D', 'E').replace('d', 'e'))
                if (kw == 'density' and 1 < value < 1e5) or (kw == 'elastic' and value > 5e5):
                    warnings.append(dict(where, message='Check %s=%g against declared N-mm-s-tonne units; heuristic only' % (kw, value)))
            except ValueError:
                pass
        if kw in ('parameter', 'parameter shape variation') or 'input' in params:
            if kw != 'include':
                warnings.append(dict(where, message='Parameters/external keyword data are not expanded; coverage is partial'))
    if step is not None:
        errors.append({'file': step['file'], 'line': step['line'], 'message': 'Missing *End Step'})
    if step_count == 0:
        warnings.append({'message': 'No *Step; may be an include/model fragment'})
    for material, where in used:
        if material not in materials:
            item = dict(where, message='Section references undefined material: ' + material)
            (warnings if incomplete else errors).append(item)
    return {'path': str(Path(path).resolve()), 'include_base': str(run_dir), 'files': files, 'keyword_count': len(sections),
            'step_count': step_count, 'units_assumed': units, 'errors': errors, 'warnings': warnings,
            'limitations': ['Static heuristic, not an Abaqus syntax/datacheck or engineering verification.',
                            'Element connectivity, parameter expansion and full keyword semantics are not validated.']}


def monitor(stem, limit=40):
    stem = Path(stem).resolve()
    report = {'job_stem': str(stem), 'files': {}, 'evidence': [], 'process_liveness_checked': False}
    failure, completed, terminated, started = False, False, False, False
    rx = re.compile(r'\*\*\*\s*ERROR|TOO MANY ATTEMPTS|TIME INCREMENT REQUIRED|ZERO PIVOT|NUMERICAL SINGULARITY|NEGATIVE EIGEN|DISTORT|OVERCONSTRAINT', re.I)
    for ext in ('log', 'sta', 'msg', 'dat', 'lck', 'odb'):
        p = Path(str(stem) + '.' + ext)
        item = {'path': str(p), 'exists': p.exists()}
        if p.is_file():
            item.update(size=p.stat().st_size, modified_epoch=p.stat().st_mtime)
            if ext in ('log', 'sta', 'msg', 'dat'):
                # Stream the whole diagnostic file; retain only bounded output.
                tail, hits = [], []
                with p.open('r', encoding='utf-8', errors='replace') as f:
                    for line in f:
                        line = line.rstrip()
                        tail.append(line)
                        tail = tail[-limit:]
                        if rx.search(line):
                            hits.append(line)
                            hits = hits[-limit:]
                        low = line.lower()
                        fail = ('***error' in low.replace(' ', '') or 'analysis has not been completed' in low
                                or 'exited with an error' in low or 'analysis exited with errors' in low
                                or 'too many attempts made' in low or 'aborted' in low)
                        done = ('the analysis has completed successfully' in low
                                or 'the analysis has been completed' in low
                                or re.search(r'abaqus job\s+.+\s+completed\s*$', low) is not None)
                        end = 'terminate request received' in low or 'terminated by' in low
                        if fail or done or end:
                            report['evidence'].append({'file': ext, 'line': line})
                            failure |= fail
                            completed |= done and not fail
                            terminated |= end
                        started |= 'begin abaqus/standard analysis' in low or 'begin abaqus/explicit analysis' in low
                item.update(tail=tail[-min(limit, 12):], diagnostic_matches=hits)
        report['files'][ext] = item
    if completed and (failure or terminated):
        status = 'conflicting_evidence'
    elif failure:
        status = 'failed'
    elif terminated:
        status = 'termination_requested_completion_unconfirmed'
    elif completed:
        status = 'completed_in_logs'
    elif started or report['files']['lck']['exists']:
        status = 'started_completion_unconfirmed'
    else:
        status = 'unknown'
    report['status'] = status
    report['note'] = 'Lock-file absence, CAE SUBMITTED status and an ODB file do not prove successful completion. Check timestamps for reused job names.'
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    check = sub.add_parser('inp-check')
    check.add_argument('path')
    check.add_argument('--units', choices=('N-mm-s-tonne',))
    check.add_argument('--include-base', help='Job submission directory; defaults to main INP parent')
    watch = sub.add_parser('monitor')
    watch.add_argument('stem', help='Absolute job path without extension')
    a = p.parse_args(argv)
    try:
        result = inp_check(a.path, a.units, a.include_base) if a.command == 'inp-check' else monitor(a.stem)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 1 if result.get('errors') else 0
    except (OSError, ValueError) as e:
        p.exit(2, str(e) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
