import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import { Root } from './components/Root';
import { Dashboard } from './components/Dashboard';
import NewNote from './components/NewNote';
import { PatientList } from './components/PatientList';
import { NoteHistory } from './components/NoteHistory';
import './App.css';

const router = createBrowserRouter([
  {
    path: '/',
    element: <Root />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'new-note', element: <NewNote /> },
      { path: 'patients', element: <PatientList /> },
      { path: 'history', element: <NoteHistory /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
