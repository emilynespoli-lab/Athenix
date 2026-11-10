document.querySelectorAll('[data-run]').forEach((element) => {
  const interval = setInterval(async () => {
    try {
      const response = await fetch(`/api/runs/${element.dataset.run}`);
      if (!response.ok) { clearInterval(interval); return; }
      const data = await response.json();
      if (!['queued', 'running'].includes(data.state)) { clearInterval(interval); location.reload(); }
    } catch (_) { clearInterval(interval); }
  }, 1800);
});
document.querySelectorAll('[data-estimate-url]').forEach((input) => {
  let timeout;
  input.addEventListener('input', () => {
    clearTimeout(timeout);
    timeout = setTimeout(async () => {
      const output = input.closest('form').querySelector('.estimate-result');
      try {
        const response = await fetch(`${input.dataset.estimateUrl}?scope=${encodeURIComponent(input.value)}`);
        const data = await response.json();
        output.textContent = response.ok ? `${data.batches} lote(s) · reserva: ${data.max_cost_usd === null ? 'preço não disponível' : 'US$ ' + data.max_cost_usd}` : data.detail;
      } catch (_) { output.textContent = 'Não foi possível estimar este escopo.'; }
    }, 400);
  });
});
