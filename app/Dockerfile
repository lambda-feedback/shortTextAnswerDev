# Base image that bundles AWS Lambda Python 3.8 image with some middleware functions
# FROM base-eval-tmp
FROM rabidsheep55/python-base-eval-layer

WORKDIR /app

RUN mkdir /usr/share/nltk_data

ARG NLTK_DATA=/usr/share/nltk_data

ENV NLTK_DATA=/usr/share/nltk_data
# Copy and install any packages/modules needed for your evaluation script.
COPY requirements.txt .
COPY brown_length .
COPY word_freqs .
COPY w2v .
RUN pip3 install -r requirements.txt
RUN python -m nltk.downloader wordnet
RUN python -m nltk.downloader word2vec_sample
RUN python -m nltk.downloader brown
RUN python -m nltk.downloader stopwords
RUN python -m nltk.downloader punkt

# Copy the evaluation and testing scripts
COPY brown_length ./app/
COPY word_freqs ./app/
COPY w2v ./app/
COPY evaluation.py ./app/
COPY evaluation_tests.py ./app/

# Copy Documentation
COPY docs/dev.md ./app/docs/dev.md
COPY docs/user.md ./app/docs/user.md

# Set permissions so files and directories can be accessed on AWS
RUN chmod 644 $(find . -type f)
RUN chmod 755 $(find . -type d)

# The entrypoint for AWS is to invoke the handler function within the app package
CMD [ "/app/app.handler" ]