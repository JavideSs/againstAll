#docker build -t webviewer -f webviewer.dockerfile .
#docker run --name webviewer -p 8080:80 webviewer
#http://localhost:8080/?addr=https://localhost:4444

FROM nginx
COPY webviewer/ /usr/share/nginx/html
EXPOSE 80