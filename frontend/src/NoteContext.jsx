import { createContext, useContext, useState } from 'react';

const NoteContext = createContext(null);

export function NoteProvider({ children }) {
  const [result, setResult] = useState(null);
  const [words, setWords] = useState([]);
  const [file, setFile] = useState(null);
  const [patientName, setPatientName] = useState('');
  const [noteType, setNoteType] = useState('soap');
  const [resultTab, setResultTab] = useState('transcript');
  const [keywords, setKeywords] = useState('');

  return (
    <NoteContext.Provider value={{
      result, setResult,
      words, setWords,
      file, setFile,
      patientName, setPatientName,
      noteType, setNoteType,
      resultTab, setResultTab,
      keywords, setKeywords,
    }}>
      {children}
    </NoteContext.Provider>
  );
}

export const useNote = () => useContext(NoteContext);
