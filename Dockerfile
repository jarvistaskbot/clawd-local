FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    curl \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js for claude CLI
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install claude CLI
RUN npm install -g @anthropic-ai/claude-code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source (no personal config/memory files)
COPY agent.py config.py context.py main.py media_handler.py memory.py \
     optimizer.py queue_manager.py subagent.py watchdog.py ./

# Persona files — mount your own at runtime:
#   docker run -v /path/to/your/workspace:/workspace ...
# Or place SOUL.md, USER.md, MEMORY.md in /workspace before starting.
RUN mkdir -p /workspace /app/media_temp

ENV WORKSPACE_DIR=/workspace
ENV MEDIA_TEMP_DIR=/app/media_temp
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
