# Analytics Lambda: curated data in S3 -> analytics -> DynamoDB.
#
# Container image rather than a zip because the analytics needs shapely and
# pyproj (native wheels with bundled GEOS/PROJ data), and because the job wants
# the 10GB ephemeral storage only image-backed functions can pair with.
#
# Build context is the repo root: the handler lives here in infrastructure/,
# but the analytics it runs lives in data-pipeline/. See .dockerignore -- the
# context must not drag in data-pipeline/data/ (tens of GB).
FROM public.ecr.aws/lambda/python:3.12

COPY data-pipeline/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# The analytics package and its config, imported unchanged.
COPY data-pipeline/src/ ${LAMBDA_TASK_ROOT}/src/
COPY data-pipeline/config/ ${LAMBDA_TASK_ROOT}/config/

# handler.py resolves config/ as a sibling, so it stays at the task root.
COPY infrastructure/modules/analytics_lambda/lambda/ ${LAMBDA_TASK_ROOT}/

ENV PYTHONPATH=${LAMBDA_TASK_ROOT}:${LAMBDA_TASK_ROOT}/src

CMD ["handler.handler"]
