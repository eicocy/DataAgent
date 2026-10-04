FROM python:3.12-slim
RUN pip install --no-cache-dir pandas==2.2.3 numpy==2.2.6 matplotlib==3.10.1 pydantic==2.11.1
COPY backend/app/sandbox/__init__.py backend/app/sandbox/validator.py backend/app/sandbox/protocol.py /usr/local/lib/python3.12/site-packages/app/sandbox/
COPY deploy/sandbox/runtime.py /opt/runtime.py
COPY deploy/sandbox/export_output.py /opt/export_output.py
RUN mkdir /output && chmod 1777 /output
LABEL datalens.sandbox.protocol="1.0"
ENV OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLCONFIGDIR=/tmp/matplotlib
USER 65532:65532
WORKDIR /output
ENTRYPOINT []
CMD ["python", "-I", "/opt/runtime.py"]
