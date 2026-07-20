import { useEffect, useState } from 'react';
import type { Lote } from '../types/lote.ts';
import { fetchLotes } from '../services/lotesService.ts';
export function useLotes(){ const [lotes,setLotes]=useState<Lote[]>([]); const [loading,setLoading]=useState(true); const [error,setError]=useState(''); useEffect(()=>{ fetchLotes().then(setLotes).catch(e=>setError(e.message)).finally(()=>setLoading(false));},[]); return {lotes,loading,error};}
