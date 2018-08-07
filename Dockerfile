FROM python:3

WORKDIR /opt/hp-irs

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY . /opt/hp-irs/

ENV PYTHONUNBUFFERED=TRUE

EXPOSE 5000/tcp
EXPOSE 5000/udp

CMD [ "python", "./IRS_Cli.py" ]

