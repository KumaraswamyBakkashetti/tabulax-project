import React, { useState } from "react";
import { useDropzone } from 'react-dropzone';
import { FileUp, Database, Code, Download, X, ArrowRight, Wand2, LogOut } from 'lucide-react';
import './index.css';

// Components
import DatabaseConnect from './components/DatabaseConnect';
import ColumnSelector from './components/ColumnSelector';
import ExampleInput from './components/ExampleInput';
import TransformResult from './components/TransformResult';
import LandingPage from './components/LandingPage';
import MongoConnect from './components/MongoConnect';
import { useAuth } from './components/AuthContext';

// Shared ConnectionInfo type
interface ConnectionInfo {
  host?: string;
  port?: string;
  user?: string;
  password?: string;
  database?: string; 
  table?: string;    
  uri?: string;      
}

function App() {
  const { isAuthenticated, user, logout } = useAuth();
  
  const [file, setFile] = useState<File | null>(null);
  const [columns, setColumns] = useState<string[]>([]);
  const [previewData, setPreviewData] = useState<any[]>([]);
  const [unmodifiedPreviewData, setUnmodifiedPreviewData] = useState<any[]>([]);
  const [selectedColumn, setSelectedColumn] = useState('');
  const [examples, setExamples] = useState('');
  const [classification, setClassification] = useState('');
  const [generatedCode, setGeneratedCode] = useState('');
  const [error, setError] = useState('');
  const [isUploading, setIsUploading] = useState(false);
  const [transformedColumns, setTransformedColumns] = useState<string[]>([]);
  const [transformedCsv, setTransformedCsv] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState('file'); // 'file', 'database', 'mongodb', or 'sql-view'
  const [isDatabaseMode, setIsDatabaseMode] = useState(false); // True for MySQL, could be reused or have a specific mongo one
  const [isMongoMode, setIsMongoMode] = useState(false);
  const [mongoUri, setMongoUri] = useState('mongodb://localhost:27017/');
  const [selectedMongoDb, setSelectedMongoDb] = useState('');
  const [selectedMongoCollection, setSelectedMongoCollection] = useState('');
  
  // Use the shared ConnectionInfo type for the state
  const [connectionInfo, setConnectionInfo] = useState<ConnectionInfo>({
    host: 'localhost', // Default for MySQL
    port: '3306',    // Default for MySQL
    user: 'root',     // Default for MySQL
    password: '',   // Default for MySQL
    // uri will be set for MongoDB mode
  });

  const [selectedDb, setSelectedDb] = useState('');
  const [selectedTable, setSelectedTable] = useState('');
  const [readyToUpdate, setReadyToUpdate] = useState(false);
  const [sqlContent, setSqlContent] = useState('');

  const onDrop = (acceptedFiles: File[]) => {
    if (acceptedFiles && acceptedFiles.length > 0) {
      setFile(acceptedFiles[0]);
      handleFileUploadFromDrop(acceptedFiles[0]);
    }
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'text/csv': ['.csv'],
      'application/json': ['.json'],
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/sql': ['.sql'],
      'text/plain': ['.sql']
    },
    maxFiles: 1,
    multiple: false
  });

  const handleFileUploadFromDrop = async (file: File) => {
    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const token = localStorage.getItem('token');
      const response = await fetch('http://localhost:8000/upload_file/', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: formData,
      });

      if (!response.ok) {
        let errorMessage = `HTTP error! status: ${response.status}`;
        try {
          const errorData = await response.json();
          if (errorData && errorData.detail) {
            errorMessage = errorData.detail;
          }
        } catch (e) {
          // If response is not JSON or doesn't have detail, stick with the HTTP status
        }
        throw new Error(errorMessage);
      }

      const data = await response.json();
      
      if (data.file_type === 'sql') {
        // Handle SQL file differently
        setSqlContent(data.sql_content);
        setColumns([]);
        setPreviewData([]);
        setUnmodifiedPreviewData([]);
        // Show SQL content in a formatted way
        setActiveTab('sql-view');
      } else {
        // Handle CSV, JSON, and XLSX files
        setColumns(data.columns);
        setPreviewData(data.preview);
        setUnmodifiedPreviewData(data.preview);
      }
      setError('');
    } catch (err) {
      console.error('Upload error:', err);
      setError('Failed to upload file: ' + (err as Error).message);
      setFile(null); // Reset file selection on error
    } finally {
      setIsUploading(false);
    }
  };

  // Handle manual download of transformed CSV
  const handleManualDownload = () => {
    if (!transformedCsv) {
      setError('No transformed CSV available to download');
      return;
    }
    
    const blob = new Blob([transformedCsv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'transformed_data.csv';
    a.click();
    window.URL.revokeObjectURL(url);
  };

  // Handle download from server
  const handleDownload = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('http://localhost:8000/download/', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      
      const csvText = await response.text();
      const blob = new Blob([csvText], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'transformed_data.csv';
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download error:', err);
      setError('Failed to download CSV: ' + (err as Error).message);
    }
  };

  // Dismiss error message
  const dismissError = () => setError('');
  const normalize = (s: string) => s.toLowerCase().replace(/\s+/g, '');

  const handleRemoveFile = () => {
    setFile(null);
    setColumns([]);
    setPreviewData([]);
    setUnmodifiedPreviewData([]);
    setSelectedColumn('');
    setExamples('');
    setClassification('');
    setGeneratedCode('');
    setTransformedColumns([]);
    setTransformedCsv(null);
    setError('');
    // Reset tab to file if it was sql-view or a DB view
    if (activeTab === 'sql-view' || activeTab === 'database' || activeTab === 'mongodb') {
      setActiveTab('file');
    }
    setIsDatabaseMode(false); // Reset MySQL mode
    setIsMongoMode(false); // Reset Mongo mode
    setSqlContent('');
  };

  // If not authenticated, show landing page
  if (!isAuthenticated) {
    return <LandingPage />;
  }

  // Update the file upload UI section
  const renderFileUploadSection = () => (
    <div className="mb-8 animate-slide-in">
      <h2 className="section-title flex items-center text-xl font-semibold text-neutral-700 mb-3">
        <FileUp size={20} className="mr-2 text-primary" />
        Upload Data File
      </h2>
      <div 
        {...getRootProps()} 
        className={`bg-neutral-50 rounded-lg border-2 border-dashed transition-all duration-200 ease-in-out ${ 
          isDragActive ? 'border-primary bg-blue-50 scale-105 shadow-md' : isUploading ? 'border-neutral-400' : 'border-neutral-300 hover:border-primary/70'
        } ${file ? 'p-4' : 'p-8'}`}
      >
        <input {...getInputProps()} className="hidden" />
        <div className={`text-center ${file ? 'px-2' : ''}`}>
          {isUploading ? (
            <div className="flex flex-col items-center justify-center h-24">
              <div className="animate-spin rounded-full h-10 w-10 border-t-2 border-b-2 border-primary"></div>
              <p className="mt-3 text-sm text-neutral-600">Uploading...</p>
            </div>
          ) : file ? (
            <div className="flex items-center justify-between w-full h-24">
              <div className="flex items-center space-x-3 overflow-hidden mr-2">
                <FileUp size={28} className="text-primary flex-shrink-0" />
                <div>
                  <p className="text-md font-medium text-neutral-800 truncate" title={file.name}>
                    {file.name}
                  </p>
                  <p className="text-xs text-neutral-500">({(file.size / 1024).toFixed(1)} KB)</p>
                </div>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation(); // Prevent dropzone activation
                  handleRemoveFile();
                }}
                className="p-1.5 rounded-full text-neutral-500 hover:bg-red-100 hover:text-red-600 transition-colors duration-150 flex-shrink-0"
                title="Remove file"
              >
                <X size={18} />
              </button>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-24">
              <svg className="mx-auto h-12 w-12 text-neutral-400 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <p className="mt-2 text-sm text-neutral-600">
                Drag & drop your file here, or <span className="font-medium text-primary hover:text-primary-dark cursor-pointer">browse</span>
              </p>
              <p className="mt-1 text-xs text-neutral-500">Supported: CSV, JSON, XLSX, SQL</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-neutral-50 to-blue-100 py-8 px-4 sm:px-6 lg:px-8 text-neutral-800">
      <div className="max-w-6xl mx-auto"> {/* Increased max-width for a bit more space */}
        {/* Header */}
        <header className="flex justify-between items-center mb-10">
          <div className="text-left"> {/* Changed from text-center for alignment */}
            <h1 className="text-4xl font-bold text-neutral-900 tracking-tight">
              <span className="bg-clip-text text-transparent bg-gradient-to-r from-primary to-secondary">
                TabulaX
              </span>
            </h1>
            <p className="text-lg text-neutral-600 mt-1">
              Transform your data with ease and intelligence.
            </p>
          </div>
          {isAuthenticated && user && (
            <div className="flex items-center space-x-3">
              <div className="text-right">
                <p className="text-sm text-neutral-600">{user.username}</p>
                {/* <p className=\"text-xs text-neutral-500\">Active</p> */}
            </div>
            <button 
              onClick={logout}
                className="p-2 rounded-full hover:bg-neutral-200 text-neutral-600 hover:text-error transition-colors duration-150"
              title="Logout"
            >
                <LogOut className="h-5 w-5" />
            </button>
          </div>
          )}
        </header>

        {/* Main Content Container */}
        <main className="bg-white rounded-xl shadow-2xl overflow-hidden"> {/* Stronger shadow */}
          {/* Error Alert - No changes here for now, but could be standardized component later */}
          {error && (
            <div className="bg-red-50 border-l-4 border-error p-4 animate-fade-in">
              <div className="flex items-start">
                <div className="flex-shrink-0">
                  <svg className="h-5 w-5 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
                  </svg>
                </div>
                <div className="ml-3 flex-1">
                  <p className="text-sm text-red-700">{error}</p>
                </div>
                <div className="ml-auto pl-3">
                  <div className="-mx-1.5 -my-1.5">
                    <button
                      onClick={dismissError}
                      className="inline-flex rounded-md p-1.5 text-red-500 hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
                    >
                      <span className="sr-only">Dismiss</span>
                      <X size={16} />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Tabs */}
          {isAuthenticated && (
            <div className="border-b border-neutral-200 bg-neutral-50 rounded-t-xl">
              <nav className="flex -mb-px space-x-1 px-4">
              <button
                  onClick={() => {setActiveTab('file'); setIsDatabaseMode(false); setIsMongoMode(false);}}
                  className={`py-3 px-4 text-center border-b-2 font-semibold text-sm transition-colors duration-150 flex items-center space-x-2 ${
                  activeTab === 'file'
                    ? 'border-primary text-primary'
                      : 'border-transparent text-neutral-500 hover:text-primary hover:border-primary/50'
                }`}
              >
                  <FileUp size={16} />
                  <span>Files</span>
              </button>
              <button
                  onClick={() => {setActiveTab('database'); setIsDatabaseMode(true); setIsMongoMode(false);}}
                  className={`py-3 px-4 text-center border-b-2 font-semibold text-sm transition-colors duration-150 flex items-center space-x-2 ${
                  activeTab === 'database'
                    ? 'border-primary text-primary'
                      : 'border-transparent text-neutral-500 hover:text-primary hover:border-primary/50'
                }`}
              >
                  <Database size={16} />
                  <span>Database</span>
                </button>
                <button
                  onClick={() => {setActiveTab('mongodb'); setIsDatabaseMode(false); setIsMongoMode(true);}}
                  className={`py-3 px-4 text-center border-b-2 font-semibold text-sm transition-colors duration-150 flex items-center space-x-2 ${
                    activeTab === 'mongodb'
                      ? 'border-primary text-primary'
                      : 'border-transparent text-neutral-500 hover:text-primary hover:border-primary/50'
                  }`}
                >
                  <Database size={16} /> {/* Replace with a MongoDB icon if available */}
                  <span>MongoDB</span>
              </button>
            </nav>
          </div>
          )}

          <div className="p-6 md:p-8"> {/* Increased padding */}
            {!isAuthenticated ? (
                <LandingPage />
            ) : activeTab === 'database' ? (
              <DatabaseConnect 
                setColumns={setColumns}
                setPreviewData={setPreviewData}
                setUnmodifiedPreviewData={setUnmodifiedPreviewData}
                selectedColumn={selectedColumn}
                generatedCode={generatedCode}
                setTransformedCsv={setTransformedCsv}
                setIsDatabaseMode={setIsDatabaseMode}
                setConnectionInfo={setConnectionInfo}
                setSelectedDb={setSelectedDb}
                setSelectedTable={setSelectedTable}
                connectionInfo={connectionInfo}
                selectedDb={selectedDb}
                selectedTable={selectedTable}
              />
            ) : activeTab === 'mongodb' ? (
              <MongoConnect 
                setColumns={setColumns}
                setPreviewData={setPreviewData}
                setUnmodifiedPreviewData={setUnmodifiedPreviewData}
                setIsMongoMode={setIsMongoMode}
                mongoUri={mongoUri}
                setMongoUri={setMongoUri}
                setSelectedMongoDb={setSelectedMongoDb}
                setSelectedMongoCollection={setSelectedMongoCollection}
                selectedMongoDb={selectedMongoDb}
                selectedMongoCollection={selectedMongoCollection}
                selectedColumn={selectedColumn}
                generatedCode={generatedCode}
              />
            ) : activeTab === 'sql-view' ? (
              <div className="mb-8 animate-slide-in">
                <h2 className="section-title flex items-center">
                  <Code size={18} className="mr-2 text-primary" />
                  SQL Content
                </h2>
                <pre className="bg-gray-50 p-4 rounded-lg overflow-x-auto">
                  <code className="text-sm">{sqlContent}</code>
                </pre>
              </div>
            ) : (
              renderFileUploadSection()
            )}

            {/* Transformation Section */}
            {columns.length > 0 && (
              <div className="mb-8 rounded-lg border border-neutral-200 bg-white p-6 shadow-lg animate-slide-in">
                <h2 className="section-title flex items-center text-xl font-semibold text-neutral-700 mb-5">
                  <Wand2 size={20} className="mr-2 text-accent" />
                  Define Transformation
                </h2>
                <div className="space-y-6">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 items-start">
                    <div className="space-y-4 p-4 bg-neutral-50 rounded-lg border border-neutral-200">
                      <ColumnSelector 
                        columns={columns}
                        selectedColumn={selectedColumn}
                        setSelectedColumn={setSelectedColumn}
                      />
                      
                      <ExampleInput 
                        selectedColumn={selectedColumn}
                        examples={examples}
                        setExamples={setExamples}
                        setClassification={setClassification}
                        setGeneratedCode={setGeneratedCode}
                      />
                    </div>
                    
                    <div className="sticky top-6">
                      {classification && (
                        <div className="p-4 bg-gradient-to-br from-blue-50 to-indigo-50 rounded-lg border border-blue-200 shadow-md animate-fade-in">
                          <h3 className="text-md font-semibold text-neutral-700 mb-2 flex items-center">
                            <Code size={18} className="mr-2 text-primary" />
                            Detected Pattern
                          </h3>
                          <div className="p-3 bg-white rounded-md shadow-sm">
                            <div className="flex items-center">
                              <div className="w-2.5 h-2.5 bg-primary rounded-full mr-2.5 shrink-0"></div>
                              <p className="text-neutral-800 font-medium text-sm">{classification}</p>
                            </div>
                            {/* <p className=\"text-xs text-neutral-500 mt-1.5\">
                              The transformation function will be tailored for this pattern.
                            </p> */}
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                  
                  <TransformResult 
                    selectedColumn={selectedColumn}
                    code={generatedCode}
                    setTransformedPreview={setPreviewData}
                    transformedPreview={previewData}
                    isDatabaseMode={isDatabaseMode || isMongoMode}
                    isMongoMode={isMongoMode}
                    connectionInfo={
                      isMongoMode 
                        ? { uri: mongoUri, database: selectedMongoDb, table: selectedMongoCollection }
                        : { ...connectionInfo, database: selectedDb, table: selectedTable }
                    }
                    selectedDb={isMongoMode ? selectedMongoDb : selectedDb}
                    selectedTable={isMongoMode ? selectedMongoCollection : selectedTable}
                    setReadyToUpdate={setReadyToUpdate}
                    originalPreview={unmodifiedPreviewData}
                    setTransformedColumns={setTransformedColumns}
                  />
                </div>
              </div>
            )}

            {/* CSV Preview */}
            {previewData.length > 0 && (
              <div className="animate-slide-in mt-10">
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-xl font-semibold text-neutral-700 flex items-center m-0">
                    <Code size={20} className="mr-2 text-neutral-600" />
                    Data Preview
                  </h2>
                  
                  {transformedCsv && (
                    <div className="flex space-x-2">
                      <button
                        onClick={handleManualDownload}
                        className="btn bg-neutral-700 text-white hover:bg-neutral-800 focus:ring-neutral-500 text-sm py-2 px-3.5"
                      >
                        <Download size={16} className="mr-1.5" />
                          Download Results
                      </button>
                    </div>
                  )}
                </div>
                
                <div className="bg-white rounded-lg overflow-hidden shadow-xl border border-neutral-200">
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-neutral-200">
                      <thead className="bg-neutral-50">
                        <tr>
                          {previewData.length > 0 && Object.keys(previewData[0]).map((key) => {
                            const isSelectedBase = normalize(key) === normalize(selectedColumn);
                            const isTransformed = transformedColumns.some(col => normalize(col) === normalize(key));
                            // A column is the target of transformation if it's selected AND code has been generated for it
                            const isTransformationTarget = isSelectedBase && generatedCode;

                            let thClass = 'px-5 py-3 text-left text-xs font-semibold uppercase tracking-wider whitespace-nowrap ';

                            if (isTransformationTarget && isTransformed) {
                              // Column was selected, code generated, and transformation applied (now shows transformed data)
                              thClass += 'bg-gradient-to-r from-green-50 via-green-100 to-green-100 text-green-800';
                            } else if (isTransformationTarget) {
                              // Column is selected and code generated, but not yet applied (or reverted)
                              thClass += 'bg-gradient-to-r from-yellow-50 via-yellow-100 to-yellow-100 text-yellow-800';
                            } else if (isTransformed) {
                              // Other columns that might be affected by transformation (e.g. new columns)
                              thClass += 'bg-neutral-100 text-neutral-700'; 
                            } else {
                              thClass += 'text-neutral-600';
                            }

                            return (
                              <th key={key} className={thClass}>
                                {key}
                                {isTransformationTarget && isTransformed && (
                                  <span className="ml-1.5 px-1.5 py-0.5 bg-green-200 text-green-800 rounded-full text-[10px] font-medium">Transformed</span>
                                )}
                                {isTransformationTarget && !isTransformed && (
                                  <span className="ml-1.5 px-1.5 py-0.5 bg-yellow-200 text-yellow-800 rounded-full text-[10px] font-medium">Selected</span>
                                )}
                              </th>
                            );
                          })}
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-neutral-200">
                        {previewData.map((row, index) => (
                          <tr key={index} className="hover:bg-neutral-50 transition-colors duration-150">
                            {Object.entries(row).map(([key, value]) => {
                              const isSelectedBase = normalize(key) === normalize(selectedColumn);
                              const isTransformed = transformedColumns.some(col => normalize(col) === normalize(key));
                              const isTransformationTarget = isSelectedBase && generatedCode; 

                              let tdClass = 'px-5 py-3.5 whitespace-nowrap text-sm ';

                              if (isTransformationTarget && isTransformed) {
                                tdClass += 'bg-green-50 text-green-800 font-medium';
                              } else if (isTransformationTarget) {
                                tdClass += 'bg-yellow-50 text-yellow-800';
                              } else if (isTransformed) {
                                tdClass += 'bg-neutral-50 text-neutral-800'; 
                              } else {
                                tdClass += 'text-neutral-700';
                              }
                              
                              return (
                                <td key={key} className={tdClass}>
                                {String(value)}
                              </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {previewData.length > 0 && (
                    <div className="py-2.5 px-4 bg-neutral-50 text-xs text-neutral-500 border-t border-neutral-200">
                      Showing {previewData.length} preview rows. {transformedColumns.length > 0 ? `Column(s) ${transformedColumns.join(', ')} affected by transformation.` : ''}
                  </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </main>

        {/* Footer */}
        <div className="mt-8 text-center text-sm text-gray-500">
          <p>CSV Transformation Studio — Transform your data with ease</p>
        </div>
      </div>
    </div>
  );
}

export default App;