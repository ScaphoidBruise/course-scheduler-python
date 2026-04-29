# Screenshots checklist

Drop your images into `presentation/screenshots/` with these exact filenames.
The build script will swap them in automatically. Anything missing renders
as a labeled placeholder so the deck still opens cleanly.

Recommended capture: 1600x900 (16:9) PNG with the browser zoomed so a
real term has data on screen.

| Filename                  | Where to capture                                                          |
| ------------------------- | ------------------------------------------------------------------------- |
| `hero_schedule.png`       | `/` Schedule page with weekly grid populated and a conflict warning       |
| `feature_schedule.png`    | Schedule page tighter crop on the grid (slide 3 thumbnail)                |
| `feature_catalog.png`     | `/catalog` showing the filter bar and a course detail modal               |
| `feature_profile.png`     | `/profile` after a transcript import (GPA / course list visible)          |
| `feature_progress.png`    | `/progress` showing Completed / In progress / Remaining cards             |
| `feature_planner.png`     | `/planner` with multi-term roll-up and the AI advisor visible             |
| `pytest_output.png`       | Terminal screenshot of `python -m pytest tests/ -v` finishing green       |

Tips
- On Windows, use `Win + Shift + S` and pick "Window" mode for clean edges.
- Hide your bookmarks bar before capturing the hero shot.
- For the pytest screenshot, set the terminal to dark theme and a 14pt mono font for readability.

Run the build any time to regenerate `slides.pptx`:

```powershell
python presentation\build_deck.py
```
