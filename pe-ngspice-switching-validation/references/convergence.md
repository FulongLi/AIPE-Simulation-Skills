# Convergence and fidelity

Use a maximum step small enough to resolve switching and the fastest model
time constant; the example uses 100 ns against a 10 us switching period. Repeat
with a 50 ns maximum step and compare the same final window. Inspect adjacent
late windows and inductor current, not merely a successful process exit.

DC equilibrium and energy balance must agree with the chosen nonidealities.
The example diode drop and series resistances shift output below the ideal 24 V;
it is not a MOSFET loss model. Startup resonance is not a closed-loop response.
Add parasitic L/C and validated device models only when the engineering question
requires them; document their source and operating-temperature assumptions.

Primary sources reviewed 2026-10-07: [ngspice manual and versioned manuals](https://ngspice.sourceforge.io/docs.html),
[licensing and development](https://ngspice.sourceforge.io/devel.html).
Platform: Windows, Linux and macOS distributions exist; record the actual version.
The v0.1 netlist is exercised in Ubuntu CI. Local execution is optional when
ngspice is absent, and a skipped test is not a completed solver run.
