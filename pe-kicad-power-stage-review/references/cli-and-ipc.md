# KiCad interfaces

Reviewed 2026-10-07 against the [stable KiCad 9 CLI manual](https://docs.kicad.org/9.0/en/cli/cli.html):

```sh
kicad-cli version
kicad-cli sch erc --exit-code-violations -o erc.rpt design.kicad_sch
kicad-cli pcb drc --exit-code-violations -o drc.rpt design.kicad_pcb
kicad-cli pcb export gerbers -o gerbers/ design.kicad_pcb
```

Inspect `--help` for the installed release. Reports can contain violations even
when a command exits successfully without the exit-code flag. Check zone refill,
board connectivity and the configured stackup/rules before interpreting reports.

The [official IPC API](https://dev-docs.kicad.org/en/apis-and-binding/ipc-api/for-addon-developers/)
starts in KiCad 9 and expands by version. Stable 9 IPC controls a running GUI;
do not borrow nightly `api-server` or future schematic operations as if every
stable release supports them. SWIG `pcbnew` code is version-sensitive.

[mixelpixx/KiCAD-MCP-Server](https://github.com/mixelpixx/KiCAD-MCP-Server) is MIT,
observed commit `cbb59a6203997f5e916be7e0480d63fe5519134a` on 2026-10-01.
Upstream quick start specifies KiCad 9+, Node 18+ and Python 3.11+, and claims
Windows/Linux/macOS. It supplies schematic/PCB operations, ERC/DRC, export and
optional routing/parts integrations. Evaluated only: no AIPE execution or
cross-platform compatibility test was performed.

The server can mutate project/library files and invoke subprocess/network
services. Pin a reviewed release, restrict it to scratch project directories,
disable unused services, and inspect diffs/reports. Direct CLI remains simpler
for fixed check/export jobs. Do not vendor the connector into this skill.
