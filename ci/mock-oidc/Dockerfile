# Test-only OpenID Connect provider for the e2e stack (ci/compose.e2e.yml).
# Standard library only; same digest-pinned base image as the backend.
FROM python:3.12-slim-bookworm@sha256:6a0e06f5ba0b373d051aabd3fffb9b873f27f9a2a3a14bcbe37dee6f0e3bbc70
COPY server.py /mock/server.py
USER nobody
EXPOSE 9000
HEALTHCHECK --interval=5s --timeout=3s --retries=20 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9000/healthz', timeout=2)"
CMD ["python", "/mock/server.py"]
