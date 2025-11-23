FROM python:3.9
RUN git clone -b IXALL-Userbot https://github.com/xallmean/ubot /home/ixalluserbot/ \
    && chmod 777 /home/ixalluserbot \
    && mkdir /home/ixalluserbot/bin/

COPY ./sample_config.env ./config.env* /home/ixalluserbot/

WORKDIR /home/ixalluserbot/

RUN pip install --upgrade pip
RUN pip install --upgrade pip setuptools wheel
RUN pip install av
RUN pip install av --no-binary av
RUN pip install -r requirements.txt

CMD ["bash","start"]
