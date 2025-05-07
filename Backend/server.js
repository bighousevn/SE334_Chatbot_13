require("dotenv").config();
const express = require("express");
const mongoose = require("mongoose");
const axios = require("axios");
const cors = require("cors");
const winston = require("winston");
const { v4: uuidv4 } = require("uuid");

// Cấu hình logging
const logger = winston.createLogger({
  level: "info",
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.json()
  ),
  transports: [
    new winston.transports.Console(),
    new winston.transports.File({ filename: "chatbot.log" }),
  ],
});

// Khởi tạo Express
const app = express();

// Middleware
app.use(
  cors({
    origin: process.env.FRONTEND_URL || "*",
  })
);
app.use(express.json());
app.use((req, res, next) => {
  req.requestId = uuidv4();
  logger.info(`${req.method} ${req.url}`, { requestId: req.requestId });
  next();
});

// Kết nối MongoDB với retry logic
const connectWithRetry = async () => {
  try {
    await mongoose.connect(
      process.env.MONGODB_URI || "mongodb://localhost:27017/chatbot",
      {
        useNewUrlParser: true,
        useUnifiedTopology: true,
        retryWrites: true,
        w: "majority",
      }
    );
    logger.info("✅ Đã kết nối MongoDB");
  } catch (err) {
    logger.error("❌ Lỗi kết nối MongoDB:", err);
    setTimeout(connectWithRetry, 5000);
  }
};
connectWithRetry();

// API Health Check
app.get("/health", (req, res) => {
  res.status(200).json({
    status: "healthy",
    rasa: process.env.RASA_URL || "http://localhost:5005",
    mongo: mongoose.connection.readyState === 1,
  });
});

// API Chat chính
app.post("/chat", async (req, res) => {
  try {
    const { message, sender } = req.body;

    // Validate input
    if (!message) {
      logger.warn("Thiếu trường message", { requestId: req.requestId });
      return res.status(400).json({ error: "Thiếu trường 'message'" });
    }

    const sessionId = sender || req.requestId;

    // Gọi Rasa API
    const rasaResponse = await axios.post(
      `${
        process.env.RASA_URL || "http://localhost:5005"
      }/webhooks/rest/webhook`,
      {
        sender: sessionId,
        message: message,
      },
      {
        timeout: 3000,
        headers: {
          "Content-Type": "application/json",
          "X-Request-ID": req.requestId,
        },
      }
    );

    // Lưu lịch sử chat
    await saveChatHistory(req, sessionId, message, rasaResponse.data);

    // Format response
    const botResponses = rasaResponse.data.map((r) => ({
      text: r.text,
      image: r.image,
      buttons: r.buttons,
    }));

    res.json({
      responses: botResponses,
      sessionId,
    });
  } catch (err) {
    logger.error("🔥 Lỗi xử lý chat:", {
      error: err.message,
      stack: err.stack,
      requestId: req.requestId,
    });

    const statusCode = err.response?.status || 500;
    res.status(statusCode).json({
      error: "Lỗi hệ thống",
      details: statusCode === 500 ? null : err.response?.data,
    });
  }
});

// Hàm lưu lịch sử chat
async function saveChatHistory(req, sessionId, userMessage, botResponses) {
  try {
    await mongoose.connection.db.collection("conversations").insertOne({
      sessionId,
      userMessage,
      botResponses,
      timestamp: new Date(),
      metadata: {
        ip: req.ip,
        userAgent: req.get("User-Agent"),
      },
    });
    logger.info("✅ Đã kết nối MongoDB");
  } catch (err) {
    logger.error("Lỗi lưu lịch sử chat:", err);
  }
}

// Xử lý lỗi toàn cục
app.use((err, req, res, next) => {
  logger.error("🔥 Lỗi server:", {
    error: err.message,
    stack: err.stack,
    requestId: req.requestId,
  });
  res.status(500).json({ error: "Lỗi server nội bộ" });
});

// Khởi động server
const PORT = process.env.PORT || 3000;
const server = app.listen(PORT, () => {
  logger.info(`🚀 Server chạy tại http://localhost:${PORT}`);
});

// Xử lý shutdown
process.on("SIGTERM", () => {
  logger.info("🛑 Nhận tín hiệu tắt server");
  server.close(() => {
    mongoose.connection.close(false);
    logger.info("🔌 Đã ngắt kết nối MongoDB");
    process.exit(0);
  });
});

module.exports = server;
