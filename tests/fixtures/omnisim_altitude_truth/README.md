# OmniSim altitude truth fixture

This simulator-neutral fixture captures three poses from a scripted camera rig in OmniSim 8.1.6.
The rig used an ENU world with gravity disabled, so each recorded position is the supervisor's
readback of an authored pose rather than the result of a flight or terrain model. No OmniSim
runtime is needed to run the tests.

`truth.json` contains the measured camera poses, UTC timestamps, a 334 m takeoff elevation, and
the corresponding relative and absolute altitudes. `absolute_altitude.srt.txt` expresses those
same heights with an unqualified `altitude` field; `relative_altitude.srt.txt` uses the explicit
`rel_altitude` spelling. They should produce identical frame tags.

RGB was intentionally omitted: issue #675 concerns altitude interpretation, and image pixels
would add weight without strengthening the regression. The camera's horizontal field of view is
retained so the tests can quantify the resulting footprint error.
