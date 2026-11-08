import assert from 'node:assert';
import React from 'react';
import ReactDOMServer from 'react-dom/server';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

console.log('🧪 Iniciando suite de pruebas de renderizado Markdown (Frontend)...');

// Recreamos la configuración idéntica a MarkdownRenderer para pruebas unitarias deterministas
const components = {
  h1: ({ children }) => React.createElement('h1', { className: 'text-base font-bold my-2 text-foreground border-b border-border/40 pb-1' }, children),
  h2: ({ children }) => React.createElement('h2', { className: 'text-sm font-bold my-2 text-foreground' }, children),
  h3: ({ children }) => React.createElement('h3', { className: 'text-xs sm:text-sm font-semibold my-1.5 text-primary' }, children),
  p: ({ children }) => React.createElement('p', { className: 'mb-2 last:mb-0 leading-relaxed text-foreground/95' }, children),
  ul: ({ children }) => React.createElement('ul', { className: 'list-disc pl-5 my-2 space-y-1 text-foreground/90' }, children),
  ol: ({ children }) => React.createElement('ol', { className: 'list-decimal pl-5 my-2 space-y-1 text-foreground/90' }, children),
  li: ({ children }) => React.createElement('li', { className: 'leading-relaxed pl-0.5' }, children),
  strong: ({ children }) => React.createElement('strong', { className: 'font-semibold text-foreground' }, children),
  em: ({ children }) => React.createElement('em', { className: 'italic text-foreground/90' }, children),
  blockquote: ({ children }) => React.createElement('blockquote', { className: 'border-l-2 border-primary/60 pl-3 my-2 italic text-muted-foreground bg-muted/20 py-1 rounded-r' }, children),
  pre: ({ children }) => React.createElement(React.Fragment, null, children),
  code: ({ className, children, ...props }) => {
    const { node, ...rest } = props;
    const match = /language-(\w+)/.exec(className || '');
    const rawText = String(children).replace(/\n$/, '');
    const isMultiline = rawText.includes('\n');

    if (match || isMultiline) {
      const lang = match ? match[1] : '';
      return React.createElement(
        'div',
        { className: 'my-2.5 rounded-lg overflow-hidden border border-border/70 bg-slate-950 text-slate-100 shadow-sm' },
        lang ? React.createElement('div', { className: 'px-3 py-1 bg-slate-900/90 border-b border-slate-800 text-[10px] font-mono text-cyan-400 font-medium uppercase tracking-wider flex items-center justify-between' }, React.createElement('span', null, lang)) : null,
        React.createElement('pre', { className: 'p-3 text-slate-100 font-mono text-xs overflow-x-auto leading-relaxed' }, React.createElement('code', null, rawText))
      );
    }
    return React.createElement('code', { className: 'bg-muted/80 text-foreground font-mono text-[11px] sm:text-xs px-1.5 py-0.5 rounded border border-border/50 font-medium', ...rest }, rawText);
  },
  table: ({ children }) => React.createElement('div', { className: 'overflow-x-auto my-2.5 rounded-lg border border-border/60' }, React.createElement('table', { className: 'min-w-full text-xs divide-y divide-border/60' }, children)),
  thead: ({ children }) => React.createElement('thead', { className: 'bg-muted/50 font-semibold text-foreground' }, children),
  tbody: ({ children }) => React.createElement('tbody', { className: 'divide-y divide-border/40 bg-card/40' }, children),
  tr: ({ children }) => React.createElement('tr', { className: 'hover:bg-muted/30 transition-colors' }, children),
  th: ({ children }) => React.createElement('th', { className: 'px-3 py-2 text-left font-semibold text-foreground border-r border-border/40 last:border-0' }, children),
  td: ({ children }) => React.createElement('td', { className: 'px-3 py-2 border-r border-border/40 last:border-0 text-foreground/90' }, children),
  a: ({ href, children }) => {
    const isSafe = href && (href.startsWith('http://') || href.startsWith('https://') || href.startsWith('/'));
    if (!isSafe) {
      return React.createElement('span', { className: 'text-muted-foreground underline' }, children);
    }
    return React.createElement('a', { href, target: '_blank', rel: 'noopener noreferrer', className: 'text-primary underline hover:text-primary/80 transition-colors' }, children);
  }
};

function renderMarkdown(content) {
  return ReactDOMServer.renderToStaticMarkup(
    React.createElement(ReactMarkdown, { remarkPlugins: [remarkGfm], components }, content)
  );
}

// 1. Texto simple
{
  const out = renderMarkdown('Hola mundo');
  assert.ok(out.includes('<p') && out.includes('Hola mundo</p>'), 'Debe envolver texto simple en párrafo');
  console.log('✅ 1. Texto simple: PASS');
}

// 2. Múltiples párrafos
{
  const out = renderMarkdown('Párrafo 1\n\nPárrafo 2\n\nPárrafo 3');
  const count = (out.match(/<p /g) || []).length;
  assert.strictEqual(count, 3, 'Debe renderizar 3 párrafos separados con margen');
  console.log('✅ 2. Múltiples párrafos: PASS');
}

// 3. Lista numerada
{
  const out = renderMarkdown('1. Primero\n2. Segundo\n3. Tercero');
  assert.ok(out.includes('<ol class="list-decimal'), 'Debe generar lista ordenada con list-decimal');
  assert.strictEqual((out.match(/<li /g) || []).length, 3, 'Debe contener 3 items de lista');
  console.log('✅ 3. Lista numerada: PASS');
}

// 4. Lista con bullets
{
  const out = renderMarkdown('- Opción A\n- Opción B\n- Opción C');
  assert.ok(out.includes('<ul class="list-disc'), 'Debe generar lista desordenada con list-disc');
  assert.strictEqual((out.match(/<li /g) || []).length, 3, 'Debe contener 3 items con viñetas');
  console.log('✅ 4. Lista con viñetas: PASS');
}

// 5. Negrita
{
  const out = renderMarkdown('Texto con **palabra clave** resaltada');
  assert.ok(out.includes('<strong class="font-semibold text-foreground">palabra clave</strong>'), 'Debe renderizar strong con estilo semántico');
  console.log('✅ 5. Negrita: PASS');
}

// 6. JSON fenced
{
  const jsonContent = '{\n  "event_id": "evt_123",\n  "total_cents": 1500,\n  "applied": true\n}';
  const out = renderMarkdown('```json\n' + jsonContent + '\n```');
  assert.ok(out.includes('<span>json</span>'), 'Debe mostrar etiqueta de lenguaje json');
  assert.ok(out.includes('bg-slate-950') && out.includes('pre'), 'Debe tener contenedor de código monospace estilizado');
  assert.ok(out.includes('&quot;event_id&quot;'), 'Debe escapar comillas dentro del código de forma segura');
  console.log('✅ 6. JSON fenced: PASS');
}

// 7. Código fenced (Python)
{
  const pyCode = 'def process_webhook(event: dict):\n    return True';
  const out = renderMarkdown('```python\n' + pyCode + '\n```');
  assert.ok(out.includes('<span>python</span>'), 'Debe mostrar badge de lenguaje python');
  assert.ok(out.includes('def process_webhook'), 'Debe conservar la definición del código');
  console.log('✅ 7. Código fenced Python: PASS');
}

// 8. Markdown GFM (Tablas)
{
  const tableMd = '| Fase | Duración |\n| --- | --- |\n| CLARIFY | 5m |\n| DESIGN | 10m |';
  const out = renderMarkdown(tableMd);
  assert.ok(out.includes('<table') && out.includes('<thead') && out.includes('<tbody'), 'Debe renderizar tabla completa');
  assert.ok(out.includes('<th ') && out.includes('Fase'), 'Debe contener encabezados de tabla');
  assert.ok(out.includes('<td ') && out.includes('CLARIFY'), 'Debe contener celdas de datos');
  console.log('✅ 8. Markdown GFM (Tablas): PASS');
}

// 9. Contenido con saltos de línea e inline code
{
  const out = renderMarkdown('Línea 1 con `inline_func()`.\n\nLínea 2.');
  assert.ok(out.includes('<code class="bg-muted/80 text-foreground font-mono'), 'Debe formatear inline code');
  assert.ok(out.includes('inline_func()'), 'Debe conservar el texto del inline code');
  console.log('✅ 9. Contenido con saltos de línea e inline code: PASS');
}

// 10. Seguridad XSS y sanitización de HTML no confiable
{
  const attackVector = '<script>window.pwned=true;</script><img src="x" onerror="evil()"/><a href="javascript:alert(1)">Click</a>';
  const out = renderMarkdown(attackVector);
  assert.ok(!out.includes('<script>'), 'No debe inyectar etiquetas script ejecutables');
  assert.ok(!out.includes('onerror="evil()'), 'No debe ejecutar atributos inline de eventos');
  assert.ok(!out.includes('href="javascript:'), 'No debe permitir pseudoprotocolo javascript:');
  console.log('✅ 10. Seguridad XSS y sanitización: PASS');
}

console.log('\n🎉 TODOS LOS CASOS DE PRUEBA DEL RENDERER PASARON EXITOSAMENTE (10/10).');
