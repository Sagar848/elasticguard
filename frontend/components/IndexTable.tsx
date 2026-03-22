'use client'
import { useState, useMemo } from 'react'
import { Search, ChevronUp, ChevronDown, ChevronsUpDown, ChevronLeft, ChevronRight, Copy } from 'lucide-react'
import toast from 'react-hot-toast'

interface Index {
  index?: string
  name?: string
  health?: string
  status?: string
  pri?: string | number
  rep?: string | number
  docs_count?: string | number
  'docs.count'?: string | number
  store_size?: string
  'store.size'?: string
  [key: string]: any
}

type SortDir = 'asc' | 'desc' | null

export default function IndexTable({ indices, title = 'Indices' }: { indices: Index[]; title?: string }) {
  const [search,   setSearch]   = useState('')
  const [sortCol,  setSortCol]  = useState<string | null>(null)
  const [sortDir,  setSortDir]  = useState<SortDir>(null)
  const [page,     setPage]     = useState(1)
  const [health,   setHealth]   = useState<string>('all')
  const PAGE_SIZE = 15

  const getName  = (idx: Index) => idx.index ?? idx.name ?? ''
  const getCount = (idx: Index) => Number(idx.docs_count ?? idx['docs.count'] ?? 0)
  const getSize  = (idx: Index) => idx.store_size ?? idx['store.size'] ?? ''
  const getPri   = (idx: Index) => Number(idx.pri ?? 0)
  const getRep   = (idx: Index) => Number(idx.rep ?? 0)

  const parseSizeBytes = (s: string): number => {
    if (!s) return 0
    const v = parseFloat(s)
    const u = s.toLowerCase()
    if (u.endsWith('tb')) return v * 1e12
    if (u.endsWith('gb')) return v * 1e9
    if (u.endsWith('mb')) return v * 1e6
    if (u.endsWith('kb')) return v * 1e3
    return v
  }

  const filtered = useMemo(() => {
    let list = [...indices]
    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(i => getName(i).toLowerCase().includes(q))
    }
    if (health !== 'all') {
      list = list.filter(i => (i.health ?? '').toLowerCase() === health)
    }
    if (sortCol && sortDir) {
      list.sort((a, b) => {
        let va: any, vb: any
        switch (sortCol) {
          case 'name':    va = getName(a);          vb = getName(b);          break
          case 'health':  va = a.health ?? '';       vb = b.health ?? '';      break
          case 'docs':    va = getCount(a);          vb = getCount(b);         break
          case 'size':    va = parseSizeBytes(getSize(a)); vb = parseSizeBytes(getSize(b)); break
          case 'pri':     va = getPri(a);            vb = getPri(b);           break
          case 'rep':     va = getRep(a);            vb = getRep(b);           break
          default:        va = ''; vb = ''
        }
        if (typeof va === 'number') return sortDir === 'asc' ? va - vb : vb - va
        return sortDir === 'asc'
          ? String(va).localeCompare(String(vb))
          : String(vb).localeCompare(String(va))
      })
    }
    return list
  }, [indices, search, health, sortCol, sortDir])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const pageData   = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE)

  const setSort = (col: string) => {
    if (sortCol !== col) { setSortCol(col); setSortDir('asc'); setPage(1); return }
    if (sortDir === 'asc')  { setSortDir('desc'); return }
    if (sortDir === 'desc') { setSortCol(null); setSortDir(null); return }
  }

  const SortIcon = ({ col }: { col: string }) => {
    if (sortCol !== col) return <ChevronsUpDown size={11} style={{ opacity: .35 }} />
    if (sortDir === 'asc')  return <ChevronUp size={11} style={{ color: 'var(--accent)' }} />
    return <ChevronDown size={11} style={{ color: 'var(--accent)' }} />
  }

  const healthColor = (h: string) =>
    h === 'green' ? 'var(--green)' : h === 'yellow' ? 'var(--yellow)' : h === 'red' ? 'var(--red)' : 'var(--text-muted)'

  const healthCounts = useMemo(() => {
    const c: Record<string, number> = { green: 0, yellow: 0, red: 0 }
    indices.forEach(i => { const h = (i.health ?? '').toLowerCase(); if (h in c) c[h]++ })
    return c
  }, [indices])

  const copy = (text: string) => { navigator.clipboard.writeText(text); toast.success('Copied') }

  return (
    <div className="eg-card" style={{ padding: 0, overflow: 'hidden' }}>
      {/* Header + controls */}
      <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
          {title}
        </span>
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {filtered.length} / {indices.length}
        </span>

        {/* Health filter pills */}
        <div style={{ display: 'flex', gap: 4, marginLeft: 4 }}>
          {(['all', 'green', 'yellow', 'red'] as const).map(h => (
            <button key={h} onClick={() => { setHealth(h); setPage(1) }}
              className="eg-btn" style={{
                fontSize: 10, padding: '2px 8px',
                background: health === h ? (h === 'all' ? 'var(--accent-soft)' : `color-mix(in srgb, ${healthColor(h)} 15%, transparent)`) : 'var(--bg-raised)',
                color: health === h ? (h === 'all' ? 'var(--accent)' : healthColor(h)) : 'var(--text-muted)',
                border: `1px solid ${health === h ? (h === 'all' ? 'rgba(59,130,246,.3)' : healthColor(h)) : 'var(--border)'}`,
              }}>
              {h === 'all' ? `All (${indices.length})` : `${h} (${healthCounts[h] ?? 0})`}
            </button>
          ))}
        </div>

        {/* Search */}
        <div style={{ position: 'relative', marginLeft: 'auto' }}>
          <Search size={12} style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input className="eg-input" value={search} onChange={e => { setSearch(e.target.value); setPage(1) }}
            placeholder="Filter by name…"
            style={{ paddingLeft: 28, fontSize: 12, width: 200, padding: '5px 10px 5px 28px' }} />
        </div>
      </div>

      {/* Table */}
      <div style={{ overflowX: 'auto' }}>
        <table className="eg-table" style={{ minWidth: 600 }}>
          <thead>
            <tr>
              {[
                { key: 'name',   label: 'Index Name' },
                { key: 'health', label: 'Health' },
                { key: 'pri',    label: 'Shards (Pri)' },
                { key: 'rep',    label: 'Replicas' },
                { key: 'docs',   label: 'Docs' },
                { key: 'size',   label: 'Size' },
              ].map(col => (
                <th key={col.key} onClick={() => setSort(col.key)}
                  style={{ cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                    {col.label} <SortIcon col={col.key} />
                  </span>
                </th>
              ))}
              <th style={{ width: 60 }}></th>
            </tr>
          </thead>
          <tbody>
            {pageData.length === 0 && (
              <tr><td colSpan={7} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)', fontSize: 13 }}>No indices match your filter</td></tr>
            )}
            {pageData.map((idx) => {
              const name = getName(idx)
              const h    = (idx.health ?? '').toLowerCase()
              const hc   = healthColor(h)
              return (
                <tr key={name}>
                  <td>
                    <span className="eg-mono" style={{ fontSize: 12, color: 'var(--text-primary)', wordBreak: 'break-all' }}>{name}</span>
                  </td>
                  <td>
                    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5 }}>
                      <span style={{ width: 7, height: 7, borderRadius: '50%', background: hc, boxShadow: `0 0 4px ${hc}`, flexShrink: 0 }} />
                      <span style={{ fontSize: 11, color: hc, fontWeight: 600, textTransform: 'uppercase' }}>{h || '?'}</span>
                    </span>
                  </td>
                  <td className="eg-mono" style={{ fontSize: 12 }}>{getPri(idx)}</td>
                  <td className="eg-mono" style={{ fontSize: 12 }}>{getRep(idx)}</td>
                  <td className="eg-mono" style={{ fontSize: 12 }}>
                    {getCount(idx) > 0 ? getCount(idx).toLocaleString() : '—'}
                  </td>
                  <td className="eg-mono" style={{ fontSize: 12 }}>{getSize(idx) || '—'}</td>
                  <td>
                    <button onClick={() => copy(name)} className="eg-btn eg-btn-ghost" style={{ fontSize: 10, padding: '2px 6px' }} title="Copy index name">
                      <Copy size={9} />
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{ padding: '10px 14px', borderTop: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Showing {((page - 1) * PAGE_SIZE) + 1}–{Math.min(page * PAGE_SIZE, filtered.length)} of {filtered.length}
          </span>
          <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
            <button className="eg-btn eg-btn-ghost" style={{ padding: '4px 8px' }}
              disabled={page <= 1} onClick={() => setPage(1)}>
              «
            </button>
            <button className="eg-btn eg-btn-ghost" style={{ padding: '4px 8px' }}
              disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
              <ChevronLeft size={12} />
            </button>
            {/* Page number pills */}
            {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
              const start = Math.max(1, Math.min(page - 2, totalPages - 4))
              const p = start + i
              if (p > totalPages) return null
              return (
                <button key={p} onClick={() => setPage(p)}
                  className="eg-btn" style={{
                    padding: '4px 10px', fontSize: 12,
                    background: page === p ? 'var(--accent)' : 'var(--bg-raised)',
                    color: page === p ? '#fff' : 'var(--text-secondary)',
                    border: `1px solid ${page === p ? 'var(--accent)' : 'var(--border)'}`,
                  }}>
                  {p}
                </button>
              )
            })}
            <button className="eg-btn eg-btn-ghost" style={{ padding: '4px 8px' }}
              disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
              <ChevronRight size={12} />
            </button>
            <button className="eg-btn eg-btn-ghost" style={{ padding: '4px 8px' }}
              disabled={page >= totalPages} onClick={() => setPage(totalPages)}>
              »
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
