# Model boundaries

The example linearizes an ideal continuous-conduction buck about equilibrium.
The resistive load dissipates energy and damps the LC poles. Zero ESR, no current
limit and a continuous modulator are explicit idealizations. The output is a
small-signal perturbation, not startup. A unit duty step used mathematically is
not a physically permitted large-signal test.

For digital control, include sample/hold and computation/PWM delay before reading
phase margin. For multiple gain crossings inspect all crossings; a single margin
does not establish nonlinear stability. State rad/s versus Hz explicitly.
For boost CCM add the right-half-plane zero; for DCM rederive the operating-point
model. Never migrate a controller merely by copying gain coefficients.

Synthetic numerical checks: plant DC gain equals Vin; unloaded assumptions do
not apply to finite R; stable closed-loop poles have negative real parts; the
proportional closed-loop DC gain is `K Vin / (1 + K Vin)` with unity feedback.
Use this equality as a numerical regression, not as a design acceptance limit.

Primary interface source reviewed 2026-10-07:
[python-control documentation](https://python-control.readthedocs.io/en/latest/).
The project provides linear/nonlinear systems and response analysis; the model
in this skill remains intentionally limited to an averaged linear buck.
