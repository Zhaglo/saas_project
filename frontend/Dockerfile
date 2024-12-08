FROM nginx:alpine

# Копируем статические файлы из frontend в директорию nginx
COPY . /usr/share/nginx/html

COPY nginx.conf /etc/nginx/conf.d/default.conf
