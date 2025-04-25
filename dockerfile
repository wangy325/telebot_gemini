FROM python:3.10-slim-bullseye

# set TimeZone
# RUN apt update && DEBIAN_FRONTEND=noninteractive apt install -y tzdata
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone
EXPOSE 8443
WORKDIR /app
COPY ./*.py requirements.txt dockerfile  /app/
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python",  "main.py"]