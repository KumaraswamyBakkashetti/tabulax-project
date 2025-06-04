import React, { useState, useRef, useEffect } from "react";
import Papa from "papaparse";
import { Download, RotateCcw, Check, AlertCircle, CheckCircle, AlertTriangle, UploadCloud, X, Database, Eye, EyeOff, Loader2, Code2, Save } from "lucide-react";

// Define a specific interface for connection information (can be shared if identical to DatabaseConnect)
interface ConnectionInfo {
  host?: string;
  port?: string;
  user?: string;
  password?: string;
  database?: string;
  table?: string;
  uri?: string;
}

// Define an interface for preview data rows (example, adjust as needed)
interface PreviewDataRow {
  [key: string]: any; // Allows any string keys
}

interface TransformResultProps {
  selectedColumn: string;
  code: string;
  setTransformedPreview: (preview: PreviewDataRow[]) => void;
  transformedPreview: PreviewDataRow[];
  isDatabaseMode: boolean;
  isMongoMode?: boolean;
  connectionInfo: ConnectionInfo;
  selectedDb: string;
  selectedTable: string;
  setReadyToUpdate: (ready: boolean) => void;
  originalPreview: PreviewDataRow[]; // Prop from App.tsx, assumed to be the true original
  setTransformedColumns: (updater: (prevCols: string[]) => string[]) => void; // Changed to accept an updater function
}

const TransformResult: React.FC<TransformResultProps> = ({
  selectedColumn,
  code,
  setTransformedPreview,
  transformedPreview, // This is the data that gets updated with transformations
  isDatabaseMode,
  isMongoMode,
  connectionInfo,
  selectedDb,
  selectedTable,
  setReadyToUpdate,
  originalPreview, // Use this prop for reverting CSV mode
  setTransformedColumns, // Use this prop from App.tsx
}) => {
  const [isApplying, setIsApplying] = useState(false);
  const [showRevertMenu, setShowRevertMenu] = useState(false);
  const [transformedDataForDownload, setTransformedDataForDownload] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const revertButtonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isCodeVisible, setIsCodeVisible] = useState(true);
  const [isApplied, setIsApplied] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false); // New state for download loading

  // Click outside handler for the revert menu
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        revertButtonRef.current &&
        menuRef.current &&
        !revertButtonRef.current.contains(event.target as Node) &&
        !menuRef.current.contains(event.target as Node)
      ) {
        setShowRevertMenu(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const handleRevertClick = () => {
    setShowRevertMenu(!showRevertMenu);
  };

  const handleApply = async () => {
    if (!selectedColumn || !code) {
      setError("Please select a column and generate transformation code first.");
      return;
    }
    setIsApplying(true);
    setError(null);

    try {
      const token = localStorage.getItem('token');
      const payload = {
        code,
        selected_column: selectedColumn,
        source_type: isMongoMode ? "mongodb_stored" : isDatabaseMode ? "database" : "file",
        db_info: isDatabaseMode || isMongoMode ? {
            ...connectionInfo,
            database: selectedDb,
            table: selectedTable,
          ...(isMongoMode && { uri: connectionInfo.uri }),
          ...(isDatabaseMode && {
            host: connectionInfo.host,
            port: connectionInfo.port,
            user: connectionInfo.user,
            password: connectionInfo.password
          })
        } : undefined,
      };

      const response = await fetch('http://localhost:8000/apply/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: response.statusText }));
        throw new Error(errorData.detail || 'Failed to apply transformation');
      }

      const result = await response.json();
      if (result.preview) {
        setTransformedPreview(result.preview);
        if (result.preview.length > 0) {
          setTransformedColumns(() => Object.keys(result.preview[0]));
        }
        setIsApplied(true);
        if (setReadyToUpdate) setReadyToUpdate(true);
      } else {
        setError("Transformation applied, but no preview data returned.");
      }
    } catch (err) {
      console.error("Transformation error:", err);
      setError((err as Error).message);
      if (setReadyToUpdate) setReadyToUpdate(false);
    } finally {
      setIsApplying(false);
    }
  };

  const handleDownloadTransformedFile = async () => {
    setIsDownloading(true);
    setError(null);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('http://localhost:8000/download/', {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        // Try to parse error from backend if it sends JSON, otherwise use statusText
        let errorDetail = response.statusText;
        try {
          const errorData = await response.json();
          errorDetail = errorData.detail || errorDetail;
        } catch (e) {
          // Ignore if response is not JSON
        }
        throw new Error(errorDetail || 'Failed to download transformed data');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "transformed_data.csv"; // You can make the filename dynamic if needed
      document.body.appendChild(a); // Required for Firefox
      a.click();
      window.URL.revokeObjectURL(url);
      a.remove();

    } catch (err) {
      console.error("Download error:", err);
      setError((err as Error).message);
    } finally {
      setIsDownloading(false);
    }
  };

  const handleRevert = () => {
    setTransformedPreview(originalPreview);
    setTransformedColumns(() => (originalPreview.length > 0 ? Object.keys(originalPreview[0]) : []));
    setError(null);
    setIsApplied(false);
    if (setReadyToUpdate) setReadyToUpdate(false);
    setShowRevertMenu(false);
  };

  useEffect(() => {
    // Reset applied state if code or selected column changes
    setIsApplied(false);
    if (setReadyToUpdate) setReadyToUpdate(false);
  }, [code, selectedColumn, setReadyToUpdate]);

  if (!code) {
    return (
      <div className="p-4 bg-blue-50 border border-blue-200 rounded-md text-blue-700 text-sm flex items-center">
        <Code2 size={18} className="inline mr-2.5 shrink-0" />
        Generated Python function will appear here once examples are provided and classified.
      </div>
    );
  }

  return (
    <div className="space-y-5 p-5 bg-white rounded-lg border border-neutral-200 shadow-md">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-semibold text-neutral-700 flex items-center">
          <Code2 size={20} className="mr-2 text-primary" />
          Generated Transformation Code
        </h3>
        <button 
          onClick={() => setIsCodeVisible(!isCodeVisible)}
          className="p-1.5 rounded-md hover:bg-neutral-100 text-neutral-500 transition-colors"
          title={isCodeVisible ? "Hide Code" : "Show Code"}
        >
          {isCodeVisible ? <EyeOff size={18} /> : <Eye size={18} />}
        </button>
      </div>

      {isCodeVisible && (
        <pre className="code-block p-4 bg-neutral-800 text-neutral-100 rounded-md text-sm overflow-x-auto max-h-60">
          <code>{code}</code>
        </pre>
      )}

       {error && (
        <div className="bg-red-50 border-l-4 border-red-500 text-red-700 p-3 rounded-md flex items-start text-sm" role="alert">
          <AlertTriangle size={18} className="mr-2.5 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pt-2 border-t border-neutral-200">
        <p className={`text-sm ${isApplied ? 'text-green-600 font-medium' : 'text-neutral-500'} flex items-center`}>
          {isLoading ? (
            <><Loader2 size={16} className="animate-spin mr-2" /> Applying...</>
          ) : isApplied ? (
            <><CheckCircle size={16} className="mr-2" /> Transformation applied to preview.</>
            ) : (
            <>Apply the generated code to see a preview of the transformation.</>
            )}
        </p>
        <div className="flex items-center gap-3 flex-shrink-0">
          {isApplied && transformedPreview && transformedPreview.length > 0 && (
            <button
              onClick={handleDownloadTransformedFile}
              disabled={isDownloading || isLoading}
              className="btn bg-green-500 hover:bg-green-600 text-white text-sm py-2 px-3.5 disabled:opacity-60"
            >
              {isDownloading ? <Loader2 size={16} className="animate-spin mr-1.5" /> : <Download size={16} className="mr-1.5" />}
              {isDownloading ? 'Downloading...' : 'Download File'}
            </button>
          )}
          <button
            onClick={handleRevert}
            disabled={isLoading || !originalPreview || originalPreview.length === 0}
            className="btn bg-neutral-100 hover:bg-neutral-200 text-neutral-700 text-sm py-2 px-3.5 disabled:opacity-60"
          >
            <RotateCcw size={16} className="mr-1.5" />
            Revert
          </button>
          <button 
            onClick={handleApply}
            disabled={isLoading}
            className="btn btn-primary text-sm py-2 px-3.5 disabled:bg-primary/60"
          >
            <Save size={16} className="mr-1.5" />
            Apply to Preview
          </button>
        </div>
      </div>
    </div>
  );
};

export default TransformResult;
