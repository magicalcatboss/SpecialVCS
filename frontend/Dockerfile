# Frontend Dockerfile
FROM node:18-alpine

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json ./
RUN npm install

# Copy application code
COPY . .

# Expose port
EXPOSE 5173

# Run in dev mode (accessible from host)
CMD ["npm", "run", "dev", "--", "--host"]
