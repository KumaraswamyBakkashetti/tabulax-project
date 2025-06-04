import React, { useState, ChangeEvent } from "react";
import { AlertCircle, Lightbulb, Wand2, Zap } from 'lucide-react';

interface ExampleInputProps {
  selectedColumn: string;
  examples: string;
  setExamples: (examples: string) => void;
  setClassification: (classification: string) => void;
  setGeneratedCode: (code: string) => void;
}

const ExampleInput: React.FC<ExampleInputProps> = ({ 
  selectedColumn, 
  examples, 
  setExamples, 
  setClassification, 
  setGeneratedCode 
}) => {
  const [isClassifying, setIsClassifying] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentClassification, setCurrentClassification] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleClassify = async () => {
    if (!selectedColumn || !examples) {
      setError("Please select a column and provide examples.");
      return;
    }
    setIsClassifying(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("column", selectedColumn);
      form.append("examples", examples);

      const token = localStorage.getItem('token');
      const classifyResponse = await fetch("http://localhost:8000/classify/", {
        method: "POST",
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: form,
      });

      if (!classifyResponse.ok) {
        const errorData = await classifyResponse.json().catch(() => ({ detail: classifyResponse.statusText }));
        throw new Error(errorData.detail || `Classification failed: ${classifyResponse.statusText}`);
      }

      const classifyData = await classifyResponse.json();
      setClassification(classifyData.classification);
      setCurrentClassification(classifyData.classification);
    } catch (err) {
      console.error("Classification error:", err);
      setError("Error classifying examples: " + (err as Error).message);
    } finally {
      setIsClassifying(false);
    }
  };

  const handleGenerate = async () => {
    if (!selectedColumn || !examples || !currentClassification) {
      setError("Please classify examples first and ensure all fields are filled.");
      return;
    }
    setIsGenerating(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("column", selectedColumn);
      form.append("examples", examples);
      form.append("classification", currentClassification);

      const token = localStorage.getItem('token');
      const codeResponse = await fetch("http://localhost:8000/generate_function/", {
        method: "POST",
        headers: {
          'Authorization': `Bearer ${token}`
        },
        body: form,
      });

      if (!codeResponse.ok) {
        const errorData = await codeResponse.json().catch(() => ({ detail: codeResponse.statusText }));
        throw new Error(errorData.detail || `Code generation failed: ${codeResponse.statusText}`);
      }

      const codeData = await codeResponse.json();
      setGeneratedCode(codeData.code);
    } catch (err) {
      console.error("Generation error:", err);
      setError("Error generating function: " + (err as Error).message);
    } finally {
      setIsGenerating(false);
    }
  };

  if (!selectedColumn) {
    return (
      <div className="p-3.5 bg-yellow-50 border border-yellow-300 rounded-md text-yellow-800 text-sm flex items-center">
        <Lightbulb size={18} className="inline mr-2.5 shrink-0" /> 
        Please select a column first to provide examples.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="bg-red-50 border-l-4 border-red-500 text-red-700 p-3.5 rounded-md flex items-start text-sm" role="alert">
          <AlertCircle size={18} className="mr-2.5 shrink-0 mt-0.5" />
          <span>{error}</span>
        </div>
      )}
      <div>
        <label htmlFor="example-input" className="block text-sm font-medium text-neutral-700 mb-1.5">
          Provide Examples (one per line)
      </label>
      <textarea
          id="example-input"
          value={examples}
          onChange={(e: ChangeEvent<HTMLTextAreaElement>) => setExamples(e.target.value)}
          placeholder={`e.g., transforming "apple" to "APPLE":\napple -> APPLE\nbanana -> BANANA`}
          className="textarea w-full px-3.5 py-2.5 border border-neutral-300 rounded-md shadow-sm focus:ring-2 focus:ring-primary/50 focus:border-primary transition-colors duration-150 text-neutral-800 min-h-[100px] placeholder:text-neutral-400"
        rows={4}
        />
      </div>
      
      <div className="grid sm:grid-cols-2 gap-3">
        <button 
          onClick={handleClassify} 
          disabled={!examples.trim() || isClassifying || isGenerating}
          className="btn btn-accent w-full flex items-center justify-center text-sm py-2.5 disabled:bg-accent/60"
        >
            {isClassifying ? (
              <>
                <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Classifying...
              </>
            ) : (
              <>
              <Wand2 size={16} className="mr-2" />
                Classify Examples
              </>
            )}
        </button>
        
        <button 
          onClick={handleGenerate} 
          className="btn btn-primary w-full flex items-center justify-center text-sm py-2.5 disabled:bg-primary/60"
          disabled={!currentClassification || isGenerating || isClassifying}
        >
            {isGenerating ? (
              <>
                <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
                Generating...
              </>
            ) : (
              <>
              <Zap size={16} className="mr-2" />
                Generate Function
              </>
            )}
        </button>
      </div>
    </div>
  );
};

export default ExampleInput;