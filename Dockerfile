FROM python:3.12-slim

ARG REGISTRY

RUN apt-get update && apt-get install -y tini
RUN ln -sf /usr/share/zoneinfo/Asia/Seoul /etc/localtime

RUN mkdir /webApp
WORKDIR /webApp

COPY ./ ./

RUN adduser --system --home /home/ctem --group --uid 1000 ctem
RUN mkdir -p /home/ctem && chown ctem:ctem /home/ctem

RUN chown -R ctem:ctem .
RUN chmod -R 744 .

USER ctem

# PATH 환경변수 수정
ENV PATH="${PATH}:/home/ctem/.local/bin"

RUN pip3 install --extra-index-url ${REGISTRY} -r requirements.txt

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "main.py"]