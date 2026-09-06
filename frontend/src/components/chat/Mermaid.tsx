import { useEffect, useRef, useState } from 'react';

export function Mermaid({ source, className = '' }: { source: string; className?: string }): JSX.Element {
	const containerRef = useRef<HTMLDivElement | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		let mounted = true;
		let renderId = `mermaid-${Date.now()}-${Math.floor(Math.random() * 10000)}`;
		async function renderMermaid(): Promise<void> {
			try {
				setError(null);
				const mermaidMod = (await import('mermaid')).default;
				mermaidMod.initialize({ startOnLoad: false, securityLevel: 'loose' });
				const normalized = source.replace(/^```(?:mermaid)?\n?|```$/g, '').trim();
				// 提前调用语法解析，让错误信息更早、更明确地暴露出来。
				await mermaidMod.parse(normalized);
				const { svg } = await mermaidMod.render(renderId, normalized);
				if (!mounted) return;
				if (containerRef.current) containerRef.current.innerHTML = svg;
			} catch (e: any) {
				console.error('Mermaid render error', e);
				if (!mounted) return;
				setError(String(e?.message ?? e));
			}
		}
		renderMermaid();
		return () => {
			mounted = false;
		};
	}, [source]);

	return (
		<div className={className}>
			{error ? (
				<pre className="p-2 text-xs bg-red-50 text-red-700">Mermaid 渲染失败：{error}</pre>
			) : (
				<div ref={containerRef} className="mermaid-render" />
			)}
		</div>
	);
}

export default Mermaid;
