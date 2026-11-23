"""Portable source completeness checks; no site, Git history or private manifest."""
import ast
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
SKIP={'.git','node_modules','__pycache__','.pytest_cache','.mypy_cache','.ruff_cache','dist','build'}

def check():
    errors=[]
    counts=dict(python=0,javascript=0,json=0)
    for path in sorted(ROOT.rglob('*')):
        relative=path.relative_to(ROOT)
        if any(part in SKIP for part in relative.parts) or not path.is_file():continue
        if path.is_symlink():errors.append(str(relative)+': unexpected symlink')
        if any(part in {'.state','.secrets','sites','backups','logs'} for part in relative.parts):
            errors.append(str(relative)+': private/generated path')
        if path.suffix=='.py':
            counts['python']+=1
            try:tree=ast.parse(path.read_bytes(),filename=str(relative))
            except SyntaxError:errors.append(str(relative)+': Python syntax');continue
            for node in ast.walk(tree):
                modules=[]
                if isinstance(node,ast.ImportFrom) and node.module:modules=[node.module]
                elif isinstance(node,ast.Import):modules=[a.name for a in node.names]
                for module in modules:
                    if module.startswith('cargo_management'):
                        target=ROOT.joinpath(*module.split('.'))
                        if not target.with_suffix('.py').is_file() and not target.is_dir():
                            errors.append(str(relative)+': missing '+module)
        elif path.suffix in ('.js','.cjs'):
            counts['javascript']+=1
            if subprocess.run(['node','--check',str(path)],capture_output=True).returncode:
                errors.append(str(relative)+': JavaScript syntax')
        elif path.suffix=='.json':
            counts['json']+=1
            try:json.loads(path.read_bytes())
            except ValueError:errors.append(str(relative)+': invalid JSON')
    req=json.loads((ROOT/'cargo_management/release_requirements.json').read_text())
    for folder,key,total in [('doctype','original_doctypes',31),('doctype','supporting_doctypes',2),
                             ('report','reports',16),('print_format','print_formats',2)]:
        if len(req[key])!=total:errors.append(key+': wrong count')
        for name in req[key]:
            slug=name.lower().replace(' ','_')
            path=ROOT/'cargo_management/cargo_management'/folder/slug/(slug+'.json')
            if not path.is_file() or json.loads(path.read_text()).get('name')!=name:
                errors.append('Missing definition: '+name)
    for name in ['hooks.py','setup.py','release_metadata.py','templates/cargo_invoice.html',
                 'public/images/cargo-management-logo.webp','public/images/cargo.svg',
                 'public/js/sales_invoice.js','public/js/cargo_expense_actions.js']:
        if not (ROOT/'cargo_management'/name).is_file():errors.append('Missing runtime asset: '+name)
    return dict(passed=not errors,counts=counts,errors=errors,site_accessed=False)

if __name__=='__main__':
    result=check()
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['passed'] else 1)
