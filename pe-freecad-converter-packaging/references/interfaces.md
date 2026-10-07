# Interface selection and connector evaluation

Reviewed 2026-10-07. FreeCAD provides Python scripting and a non-GUI command-line
interpreter; use the installed application's Python modules, not an unrelated
package named FreeCAD. Operations touching `FreeCADGui` need a GUI. Start from
[official scripting documentation](https://github.com/FreeCAD/FreeCAD-documentation/blob/main/wiki/Python_scripting_tutorial.md).

[neka-nat/freecad-mcp](https://github.com/neka-nat/freecad-mcp) is an MIT candidate,
with an observed commit on 2026-10-06, `8e14693a9b46b50a3656cbdd9c2922456bb3bd06`.
Its addon plus MCP server can edit models, inspect documents and execute Python.
Upstream describes Windows/Linux/macOS paths, but a comprehensive tested-version
matrix was not established. It is evaluated only, not installed or AIPE-supported.

Python execution inherits user filesystem/process privileges and the local RPC
server must not be exposed to an untrusted network. Pin the reviewed commit and
dependencies, inspect changes, and operate on project copies. Use a direct macro
for fixed geometry generation and MCP only when interactive state discovery adds
value. Full evaluation evidence is in the independent
[tool catalogue](https://github.com/FulongLi/awesome-open-source-power-electronics).

Minimal pattern inside FreeCAD: create a document, add `Part::Box`, set Length,
Width and Height from explicitly converted dimensions, `recompute()`, inspect
`Shape.isValid()`, saveAs an FCStd file, then export selected solids with Part.
A box placeholder is not a manufacturable enclosure; holes, tolerances and
keepouts require the captured engineering constraints.
