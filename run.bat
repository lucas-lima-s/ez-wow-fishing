@echo off
where uv >nul 2>nul && (uv run wow-ez-fishing %* & goto :eof)
python -m wow_ez_fishing %*
