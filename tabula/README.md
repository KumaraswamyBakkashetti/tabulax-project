# TabulaX - Data Transformation Studio

TabulaX is a powerful data transformation tool that allows you to transform your data using examples. It supports both file-based and database-based transformations with a user-friendly interface.

## Features

- User authentication with secure password storage
- File upload support (CSV, JSON, SQL)
- Direct database connection capabilities
- Example-based data transformations
- Modern, responsive UI
- Real-time data preview
- Secure data handling

## Prerequisites

- Node.js (v14 or higher)
- Python (3.8 or higher)
- MongoDB (4.4 or higher)
- MySQL (8.0 or higher)

## Setup

### Backend Setup

1. Create a virtual environment and activate it:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Start MongoDB:
   Make sure MongoDB is running on your system (default: mongodb://localhost:27017)

4. Create a `.env` file in the backend directory:
   ```
   SECRET_KEY=your-secret-key-here
   MONGODB_URL=mongodb://localhost:27017
   DATABASE_NAME=tabula
   ```

5. Start the backend server:
   ```bash
   uvicorn app:app --reload
   ```

### Frontend Setup

1. Install dependencies:
   ```bash
   cd frontend
   npm install
   ```

2. Start the development server:
   ```bash
   npm run dev
   ```

## Usage

1. Register a new account or login with existing credentials
2. Choose between file upload or database connection
3. For file upload:
   - Drag and drop or click to upload your CSV/JSON/SQL file
   - Select columns for transformation
   - Provide example transformations
   - Preview and download results

4. For database connection:
   - Enter your MySQL database credentials
   - Select database and table
   - Choose columns for transformation
   - Apply transformations
   - Save changes back to the database

## Security Features

- Password hashing using bcrypt
- JWT-based authentication
- CORS protection
- Secure password visibility toggle
- Input validation and sanitization
- Secure database connections

## Development

- Frontend: React with TypeScript
- Backend: FastAPI
- Authentication: JWT with MongoDB
- Data Storage: MySQL
- State Management: React Context
- UI Components: Custom components with Tailwind CSS

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
