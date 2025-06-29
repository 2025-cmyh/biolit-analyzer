// static/js/main.js (完整代码)

document.addEventListener('DOMContentLoaded', () => {
    // DOM Element Selection
    const searchInput = document.getElementById('search-input');
    const searchButton = document.getElementById('search-button');
    const maxResultsInput = document.getElementById('max-results-input');
    const loader = document.getElementById('loader');
    const resultsContainer = document.getElementById('results-container');
    const articlesList = document.getElementById('articles-list');
    const trendChartCanvas = document.getElementById('pub-trend-chart');
    const sortSelect = document.getElementById('sort-select');

    let trendChart = null;
    let originalArticles = [];

    // Event Listeners
    searchButton.addEventListener('click', performSearch);
    searchInput.addEventListener('keyup', (event) => {
        if (event.key === 'Enter') {
            performSearch();
        }
    });
    sortSelect.addEventListener('change', sortAndRenderArticles);

    // Main Search Function
// 【这是更正后的的全新代码块】
// 在 static/js/main.js 中，完整替换 performSearch 函数

async function performSearch() {
    const query = searchInput.value.trim();
    if (!query) {
        alert('Please enter a search term.');
        return;
    }

    // 从输入框获取 maxResults 的值
    const maxResults = maxResultsInput.value;

    loader.style.display = 'block';
    resultsContainer.style.display = 'none';
    searchButton.disabled = true;
    sortSelect.disabled = true;

    const pollForResult = (count = 0) => {
        if (count > 24) { // 最多轮询2分钟
            alert('The request is taking longer than usual. Please try again later.');
            loader.style.display = 'none';
            searchButton.disabled = false;
            sortSelect.disabled = false;
            return;
        }

        setTimeout(async () => {
            try {
                // 【关键修复】确保 fetch URL 包含了 max_results
                const response = await fetch(`/api/search?q=${encodeURIComponent(query)}&max_results=${maxResults}`);
                const result = await response.json();

                if (result.status === 'completed') {
                    const data = result.data;
                    originalArticles = data.articles;
                    renderTrendChart(data.trend_analysis, query);
                    sortSelect.value = 'impact-desc';
                    sortAndRenderArticles();
                    resultsContainer.style.display = 'block';
                    loader.style.display = 'none';
                    searchButton.disabled = false;
                    sortSelect.disabled = false;
                } else if (['pending', 'processing', 'accepted'].includes(result.status)) {
                    pollForResult(count + 1);
                } else {
                    throw new Error(result.error || 'Failed to process the query.');
                }
            } catch (error) {
                alert(`An error occurred: ${error.message}`);
                loader.style.display = 'none';
                searchButton.disabled = false;
                sortSelect.disabled = false;
            }
        }, 5000); 
    };

    pollForResult();
}

    // Sorting and Rendering
    function sortAndRenderArticles() {
        const sortBy = sortSelect.value;
        let sortedArticles = [...originalArticles];

        switch (sortBy) {
            case 'impact-desc':
                sortedArticles.sort((a, b) => b.impact_score - a.impact_score);
                break;
            case 'relevance':
                // Already sorted by relevance from API
                break;
            case 'year-desc':
                sortedArticles.sort((a, b) => b.year - a.year);
                break;
            case 'citations-desc':
                sortedArticles.sort((a, b) => b.citations - a.citations);
                break;
        }
        renderArticles(sortedArticles);
    }
    
    function renderArticles(articles) {
        if (!articles || articles.length === 0) {
            articlesList.innerHTML = '<p>No relevant articles found for this query.</p>';
            return;
        }

        const maxScore = Math.max(...articles.map(a => a.impact_score), 0);

        const articlesHTML = articles.map(article => {
            const normalizedScore = maxScore > 0 ? (article.impact_score / maxScore) * 100 : 0;
            return `
                <div class="article">
                    <h3><a href="${article.url}" target="_blank">${article.title}</a></h3>
                    <div class="article-meta">
                        <div class="impact-bar-container">
                            <div class="impact-bar" style="width: ${normalizedScore}%;"></div>
                        </div>
                        <span><strong>Impact:</strong> ${article.impact_score}</span> |
                        <span><strong>Citations:</strong> ${article.citations}</span> |
                        <span><strong>Journal:</strong> ${article.journal}</span> |
                        <span><strong>Year:</strong> ${article.year}</span>
                    </div>
                    <p><strong>Authors:</strong> ${article.authors_str}</p>
                    <div class="abstract-container">
                        <details>
                            <summary>View Abstract</summary>
                            <p class="abstract">${article.abstract_text}</p>
                        </details>
                    </div>
                </div>
            `;
        }).join('');
        articlesList.innerHTML = articlesHTML;
    }

    // Chart Rendering
    function renderTrendChart(trendData, searchInputValue) {
        if (trendChart) {
            trendChart.destroy();
        }
        
        const labels = Object.keys(trendData).sort();
        const data = labels.map(year => trendData[year]);

        const ctx = trendChartCanvas.getContext('2d');
        trendChart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Number of Articles',
                    data: data,
                    backgroundColor: 'rgba(0, 119, 182, 0.7)',
                    borderColor: 'rgba(0, 119, 182, 1)',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    title: {
                        display: true,
                        text: `Publication Trend for "${searchInputValue}"`,
                        font: { size: 16 }
                    }
                },
                scales: {
                    y: { beginAtZero: true, title: { display: true, text: 'Number of Articles' } },
                    x: { title: { display: true, text: 'Year' } }
                }
            }
        });
    }
});