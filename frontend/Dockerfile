FROM node:26.10.0-alpine

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
