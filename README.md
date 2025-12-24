# reXact-fps

**Quick downloads (latest release):**  
## Downloads (v0.4)

- **Windows** — [reXact-fps-windows-0.4.zip](https://github.com/Retzilience/reXact-fps/releases/download/0.4/reXact-fps-windows-0.4.zip)
- **Linux** — [reXact-fps-linux-0.4.tar.gz](https://github.com/Retzilience/reXact-fps/releases/download/0.4/reXact-fps-linux-0.4.tar.gz)


---

## What this is

reXact-fps is a small, focused testbed for studying timing and responsiveness in interactive systems.

It allows you to control **how often the simulation advances** (Engine FPS) and **how often frames are rendered and presented** (Visual FPS) independently, while moving a cursor using either a controller stick or a mouse. The purpose is not to benchmark peak performance or produce a single score, but to make differences in input timing, fixed-step behavior, interpolation, and presentation immediately visible and directly perceptible.

Most interactive systems—games, simulations, and UIs—silently combine several distinct clocks:

- input sampling (mouse, controller, OS),
- simulation updates (the engine advancing state),
- rendering (producing frames),
- presentation (displaying those frames).

In typical engines, these clocks are tightly coupled, hidden behind abstractions, or masked by interpolation, buffering, and frame-pacing strategies. As a result, discussions about responsiveness tend to collapse into vague or overloaded terms such as “FPS”, “input lag”, or “smoothness”, with no clear distinction between cause and effect.

reXact-fps exists to control those clocks, let you modulate them independently, and make their interactions observable. Instead of considering abstractly about refresh rates, frame generation, or latency, it provides a concrete way to see—and feel—what actually changes when each part of the pipeline is adjusted.
Input polling is coupled with the engine FPS, they are virtually the same thing in this setting.

---

## What this tool is not

It is not:

- a benchmark,
- a score-based test,
- a “best settings” advisor.

If two configurations feel different, that difference is the result—not a bug to fix.

---

## What it’s useful for

reXact-fps is useful when you want to:

- Compare how different **engine update rates** feel, independent of rendering rate.
- See how **low engine rates** introduce stepping and latency, even when visuals are smooth.
- Understand what **interpolation** does (and does not do) for responsiveness.
- Compare behavior across **different displays, sync modes, drivers, compositors, and OS setups**.

The same Engine FPS / Visual FPS numbers can feel very different depending on the full pipeline from input sampling to display update. This tool makes those differences visible instead of theoretical.

---

## Core concepts

### Engine FPS vs Visual FPS

- **Engine FPS**  
  The fixed-step simulation rate. Input is incorporated into the simulation only on these steps.

- **Visual FPS**  
  How often frames are rendered and presented.

If Visual FPS is higher than Engine FPS, multiple frames may show the same simulation state unless interpolation is enabled.  
If Engine FPS is higher than Visual FPS, the simulation can advance several steps between frames; fewer frames are shown, but each frame reflects a more recent state.

---

### Real-time reticle vs simulated dot

![Wireframe vs solid reticle visualization](https://github.com/Retzilience/reXact-fps/blob/main/assets/s1.png?raw=true)

You will see two indicators:

- **Wireframe reticle (1)**: a best-effort, “right now” estimate of your input.
- **Solid glowing dot (2)**: the simulated state, updated only on engine steps.

In controller mode, the reticle is integrated at render time from the latest stick values. When Engine FPS is low (or the engine can’t keep up), the reticle can move ahead of the simulated dot. That separation is intentional: it visualizes fixed-step latency and stair-stepping.

---

### Mouse mode and polling

Mouse mode uses a straightforward fixed-step approach: on each engine step, the simulation samples the mouse position and snaps the simulated dot to it.

This means that even if your OS cursor and display update smoothly, **the simulation only receives new mouse input at the Engine FPS cadence**. Lower Engine FPS makes this immediately visible.

---

### Interpolation

Interpolation affects rendering only.

When enabled, the rendered dot is blended between the previous and current simulated positions based on how far the main loop has progressed into the next engine step. This reduces visible stepping when Visual FPS exceeds Engine FPS, but it does **not** change when input becomes part of the simulation.

The wireframe reticle is not affected by interpolation, and the target is rendered at its simulated position for clarity.

---

## Examples that usually show differences clearly

- **Engine 120 / Visual 60** often feels more responsive than **Engine 60 / Visual 120**, even though the latter shows more frames.
- A higher engine rate means input is incorporated more frequently.
- A higher visual rate with a lower engine rate can look smoother, but responsiveness is still limited by engine steps.
- Interpolation can make low frame rates look smoother while giving a misleading sense of responsiveness.\*

\*This also makes a useful stand-in for understanding frame insertion or frame generation: extra in-between frames can look smoother, but if they don’t advance the simulation, responsiveness does not improve in the same way.

---

## Performance and limits

The maximum achievable Engine FPS and Visual FPS depend on your system and display pipeline. The application itself is lightweight (pygame), but very high resolutions or very high target rates may not be attainable.

If you are not reaching a desired **Engine FPS**, try setting **Visual FPS very high or to 0 (uncapped)** while testing. A low Visual FPS cap can effectively become the pacing ceiling for the main loop; lifting that ceiling can make it easier to see what the simulation can actually sustain.

The on-screen measured Engine and Visual rates reflect what the program is actually achieving, not what you requested.

---

## How to use it

### Recommended: use the prebuilt binaries

The recommended way to use reXact-fps is to **download the binary release for your operating system** from the releases page.

The releases are built with **Nuitka**, which compiles Python modules to C and produces a native executable. In practice this reduces overhead and typically runs better than running the same code directly from source with the Python interpreter.

If you just want to use the tool, this is the simplest and most representative way to do it.

---

### Running from source (if you want to)

If you prefer running from self-verified source, it is still recommended to build the application with Nuitka yourself, using the same approach as the official releases. This keeps behavior and performance closer to what the tool is intended to demonstrate.

Running directly via `python main.py` works, but you should expect slightly different performance characteristics compared to the released binaries.

---

## Controls

- **Shift** — Toggle the main HUD  
- **Ctrl** — Toggle mouse mode  
- **I** — Toggle interpolation  
- **Esc** — Close dialogs / exit  
- **Mouse wheel / PgUp / PgDn** — Scroll in dialogs  

---

## Notes

- **Visual FPS = 0** means uncapped presentation.
- Measured rates are what the program actually achieves, not targets.
- Differences you see between configurations are the point of the tool, not a problem to “fix”.

---

## License

Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0).

Non-commercial use only. Derivative works and redistributions must credit the original project and creator and must be shared under the same license.
