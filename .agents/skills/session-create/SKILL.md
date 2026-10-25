---
name: session-create
description: Create a learning-session-transcriber session folder from pasted text or an image of the source material, and move a PDF into that folder. Use when the user pastes session content, a class listing, video links, or a screenshot and asks to create a session, session folder, or session.yaml.
---

# Create Session

Create `sessions/<content_name>/` and fill its files. Do not run the pipeline and do not edit pipeline code.

## Required input

The user pastes text or an image of the source session. Read the image when one is attached. Three inputs are required:

- `content_name`: the session name written in the source, or the name the user states. Do not build it from a prefix, a folder pattern, or another session.
- video URLs, in the order shown. At least one.
- a PDF path: a real `.pdf` file the user provides. A filename read from the source is not a path.

If any of the three is missing, or more than one name fits, stop and ask once for only the missing items. Do not create the folder until all three are present. Do not invent a name, a URL, a title, or a PDF path.

If `sessions/<content_name>/` already exists, stop and ask. Do not overwrite it.

## Files

Work from the repo root. Copy `templates/session/` to `sessions/<content_name>/`, then fill the copy:

- `session.yaml`: replace `<content_name>` with the folder name and `<pdf_filename>` with the moved PDF's filesystem name. The template has two video blocks (`<url_1>`, `<url_2>`). Keep exactly one block per URL, in the order given, with `index` 1, 2, 3, and so on: delete unused blocks and copy the last block for extra URLs (sessions usually have 4 or 5). Leave `topic` and each video `title` empty. A filename printed next to a URL is not a title, so do not put it in `title` and do not use it as a label. For Google Drive links, write `url` as `https://drive.google.com/file/d/<id>`: drop `/view` and any query such as `?usp=drive_link`. Keep any other URL as given. Keep the other fields as in the template.
- `prompts.yaml`: leave it unchanged.
- `command.md`: replace `<content_name>` in both commands.

The result is a flat folder: `session.yaml`, `prompts.yaml`, `command.md`, and the PDF.

If the filled files need a format check, look at an existing `sessions/*/session.yaml` that is already there. Use it only as a shape example. Do not copy its name, URLs, or PDF filename. Skip folders that have no `session.yaml`. If none exist, the template is enough.

## PDF

The path must exist and end in `.pdf`. If it does not, stop and ask before creating anything.

Move the file into the session folder and keep its filename. Do not rename it. Set `include_resources.pdf` to `Path.name` of the moved file. Do not retype the filename: macOS often stores a different Unicode form than the path the user pasted, and the loader resolves that exact name.

## Verify

From the repo root, confirm the new session loads:

```bash
python -c "from pathlib import Path; from learning_session_transcriber.sessions import load_session_config as load; print(load(Path('sessions/<content_name>/session.yaml')).include_resources)"
```

If it raises, fix the session files and run it again. Do not start the pipeline.

## After

Report the folder path, the files written, and the PDF that was moved. Tell the user to use `session-run` with the content name or path when they want to execute it. Do not commit `sessions/`.
