"""Static QUNAR app.py -> core.* import contract check.

Run at repository root: python scripts/verify_deployment_imports.py
Does not need Streamlit or any third-party packages.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'app.py'


def available_names(tree: ast.Module) -> set[str]:
    result: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            result.add(node.name)
        elif isinstance(node, (ast.ImportFrom, ast.Import)):
            result.update(alias.asname or alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    result.add(target.id)
                elif isinstance(target, (ast.Tuple, ast.List)):
                    result.update(x.id for x in target.elts if isinstance(x, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            result.add(node.target.id)
    return result


def main() -> int:
    if not APP.is_file():
        print('FAIL: app.py not found at repository root:', ROOT)
        return 1
    app_ast = ast.parse(APP.read_text(encoding='utf-8'), filename=str(APP))
    issues: list[str] = []
    checked = 0
    for node in ast.walk(app_ast):
        if not isinstance(node, ast.ImportFrom) or not node.module or not node.module.startswith('core.'):
            continue
        module_path = ROOT.joinpath(*node.module.split('.')).with_suffix('.py')
        if not module_path.is_file():
            issues.append(f'app.py:{node.lineno}: missing file {module_path.relative_to(ROOT)}')
            continue
        module_ast = ast.parse(module_path.read_text(encoding='utf-8'), filename=str(module_path))
        public = available_names(module_ast)
        for alias in node.names:
            if alias.name == '*':
                continue
            checked += 1
            if alias.name not in public:
                issues.append(f'app.py:{node.lineno}: from {node.module} import {alias.name} -- symbol not found in {module_path.relative_to(ROOT)}')
    if issues:
        print('FAIL: Import contract mismatches:')
        for issue in issues:
            print(' -', issue)
        print('Upload the files from the same release, retaining core/ directory structure.')
        return 1
    print(f'PASS: {checked} named core.* imports agree with deployed Python source files.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
