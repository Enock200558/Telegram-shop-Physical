from aiohttp import web
import json
from sqlalchemy import func, select

from bot.config import EnvKeys
from bot.monitoring.metrics import get_metrics
from bot.database import Database
from bot.database.models.main import Order, ShoppingCart, Goods, BitcoinAddress
from bot.logger_mesh import logger


class MonitoringServer:
    """monitoring server with UI"""

    def __init__(self, host: str = None, port: int = None):
        self.host = host or EnvKeys.MONITORING_HOST
        self.port = port or EnvKeys.MONITORING_PORT
        self.app = web.Application()
        self.runner = None
        self._setup_routes()

    def _setup_routes(self):
        """Setup routes"""
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/metrics', self.metrics_json)
        self.app.router.add_get('/metrics/prometheus', self.prometheus_handler)
        self.app.router.add_get('/dashboard', self.dashboard_handler)
        self.app.router.add_get('/events', self.events_handler)
        self.app.router.add_get('/performance', self.performance_handler)
        self.app.router.add_get('/errors', self.errors_handler)
        self.app.router.add_get('/business-metrics', self.business_metrics_handler)
        self.app.router.add_get('/background-tasks', self.background_tasks_handler)
        self.app.router.add_get('/', self.index_handler)

    def _get_base_html(self, title: str, content: str, active_page: str = "") -> str:
        """Generate base HTML with navigation"""
        nav_items = [
            ('/', 'Overview', 'overview'),
            ('/dashboard', 'Dashboard', 'dashboard'),
            ('/business-metrics', 'Business', 'business'),
            ('/background-tasks', 'Tasks', 'tasks'),
            ('/events', 'Events', 'events'),
            ('/performance', 'Performance', 'performance'),
            ('/errors', 'Errors', 'errors'),
            ('/metrics', 'Raw JSON', 'json'),
            ('/metrics/prometheus', 'Prometheus', 'prometheus'),
        ]

        nav_html = ""
        for url, label, page_id in nav_items:
            active_class = "active" if page_id == active_page else ""
            nav_html += f'<a href="{url}" class="{active_class}">{label}</a>'

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>{title} - Bot Monitoring</title>
            <meta http-equiv="refresh" content="10">
            <style>
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    background: rgba(255, 255, 255, 0.95);
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    overflow: hidden;
                }}
                .header {{
                    background: linear-gradient(135deg, #6B73FF 0%, #000DFF 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                }}
                h1 {{ 
                    font-size: 2.5em;
                    margin-bottom: 10px;
                    text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
                }}
                .nav {{
                    display: flex;
                    justify-content: center;
                    background: rgba(0,0,0,0.1);
                    padding: 0;
                    flex-wrap: wrap;
                }}
                .nav a {{
                    color: white;
                    text-decoration: none;
                    padding: 15px 20px;
                    transition: all 0.3s;
                    position: relative;
                }}
                .nav a:hover {{
                    background: rgba(255,255,255,0.1);
                }}
                .nav a.active {{
                    background: rgba(255,255,255,0.2);
                }}
                .nav a.active::after {{
                    content: '';
                    position: absolute;
                    bottom: 0;
                    left: 0;
                    right: 0;
                    height: 3px;
                    background: white;
                }}
                .content {{
                    padding: 30px;
                }}
                .metric-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 20px;
                    margin-bottom: 30px;
                }}
                .metric-card {{
                    background: white;
                    padding: 25px;
                    border-radius: 15px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                    transition: transform 0.3s, box-shadow 0.3s;
                }}
                .metric-card:hover {{
                    transform: translateY(-5px);
                    box-shadow: 0 10px 25px rgba(0,0,0,0.15);
                }}
                .metric-value {{
                    font-size: 2.5em;
                    font-weight: bold;
                    color: #6B73FF;
                    margin: 10px 0;
                }}
                .metric-label {{
                    color: #666;
                    font-size: 0.9em;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }}
                .chart {{
                    background: white;
                    padding: 25px;
                    border-radius: 15px;
                    box-shadow: 0 5px 15px rgba(0,0,0,0.1);
                    margin-bottom: 20px;
                }}
                .status-ok {{ color: #4CAF50; }}
                .status-warning {{ color: #FF9800; }}
                .status-error {{ color: #f44336; }}
                .progress-bar {{
                    width: 100%;
                    height: 30px;
                    background: #e0e0e0;
                    border-radius: 15px;
                    overflow: hidden;
                    margin-top: 10px;
                }}
                .progress-fill {{
                    height: 100%;
                    background: linear-gradient(90deg, #4CAF50, #8BC34A);
                    transition: width 0.5s;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: white;
                    font-weight: bold;
                }}
                table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-top: 20px;
                    background: white;
                    border-radius: 10px;
                    overflow: hidden;
                }}
                th {{
                    background: #6B73FF;
                    color: white;
                    padding: 15px;
                    text-align: left;
                }}
                td {{
                    padding: 12px 15px;
                    border-bottom: 1px solid #e0e0e0;
                }}
                tr:hover {{
                    background: #f5f5f5;
                }}
                .footer {{
                    text-align: center;
                    padding: 20px;
                    color: #666;
                    background: #f5f5f5;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🤖 Bot Monitoring System</h1>
                    <div class="nav">{nav_html}</div>
                </div>
                <div class="content">
                    {content}
                </div>
                <div class="footer">
                    <p>Auto-refresh every 10 seconds | Bot Monitoring v1.0</p>
                </div>
            </div>
        </body>
        </html>
        """

    async def index_handler(self, request):
        """Overview page"""
        metrics = get_metrics()
        if not metrics:
            return web.Response(text="Metrics not initialized", status=503)

        summary = metrics.get_metrics_summary()
        uptime_hours = summary.get('uptime_seconds', 0) / 3600

        # Calculate some overview stats
        total_events = sum(summary.get('events', {}).values())
        total_errors = sum(summary.get('errors', {}).values())
        error_rate = (total_errors / total_events * 100) if total_events > 0 else 0

        content = f"""
        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">System Status</div>
                <div class="metric-value status-ok">ONLINE</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Uptime</div>
                <div class="metric-value">{uptime_hours:.1f}h</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Total Events</div>
                <div class="metric-value">{total_events:,}</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Error Rate</div>
                <div class="metric-value {'status-ok' if error_rate < 1 else 'status-warning' if error_rate < 5 else 'status-error'}">
                    {error_rate:.2f}%
                </div>
            </div>
        </div>

        <div class="chart">
            <h2>Quick Stats</h2>
            <p>System is running smoothly with {total_events} processed events and {total_errors} errors.</p>
            <p>Last update: {summary.get('timestamp', 'N/A')}</p>
        </div>
        """

        html = self._get_base_html("Overview", content, "overview")
        return web.Response(text=html, content_type='text/html')

    async def events_handler(self, request):
        """Events page"""
        metrics = get_metrics()
        if not metrics:
            return web.Response(text="Metrics not initialized", status=503)

        summary = metrics.get_metrics_summary()
        events = summary.get('events', {})

        content = "<h2>📊 Event Statistics</h2>"
        content += '<div class="metric-grid">'

        for event, count in sorted(events.items(), key=lambda x: x[1], reverse=True):
            content += f"""
            <div class="metric-card">
                <div class="metric-label">{event.replace('_', ' ').title()}</div>
                <div class="metric-value">{count:,}</div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {min(count / max(events.values()) * 100, 100)}%">
                        {count}
                    </div>
                </div>
            </div>
            """

        content += '</div>'

        html = self._get_base_html("Events", content, "events")
        return web.Response(text=html, content_type='text/html')

    async def performance_handler(self, request):
        """Performance metrics page"""
        metrics = get_metrics()
        if not metrics:
            return web.Response(text="Metrics not initialized", status=503)

        summary = metrics.get_metrics_summary()
        timings = summary.get('timings', {})

        content = "<h2>⚡ Performance Metrics</h2>"

        if timings:
            content += """
            <table>
                <thead>
                    <tr>
                        <th>Operation</th>
                        <th>Average (s)</th>
                        <th>Min (s)</th>
                        <th>Max (s)</th>
                        <th>Count</th>
                    </tr>
                </thead>
                <tbody>
            """

            for op, data in sorted(timings.items()):
                avg_class = 'status-ok' if data['avg'] < 1 else 'status-warning' if data['avg'] < 3 else 'status-error'
                content += f"""
                <tr>
                    <td><strong>{op.replace('_', ' ').title()}</strong></td>
                    <td class="{avg_class}">{data['avg']:.3f}</td>
                    <td>{data['min']:.3f}</td>
                    <td>{data['max']:.3f}</td>
                    <td>{data['count']}</td>
                </tr>
                """

            content += "</tbody></table>"
        else:
            content += "<p>No performance data available yet.</p>"

        html = self._get_base_html("Performance", content, "performance")
        return web.Response(text=html, content_type='text/html')

    async def errors_handler(self, request):
        """Errors page"""
        metrics = get_metrics()
        if not metrics:
            return web.Response(text="Metrics not initialized", status=503)

        summary = metrics.get_metrics_summary()
        errors = summary.get('errors', {})

        content = "<h2>❌ Error Tracking</h2>"

        if errors:
            content += '<div class="metric-grid">'
            for error, count in sorted(errors.items(), key=lambda x: x[1], reverse=True):
                severity_class = 'status-warning' if count < 10 else 'status-error'
                content += f"""
                <div class="metric-card">
                    <div class="metric-label">{error}</div>
                    <div class="metric-value {severity_class}">{count}</div>
                </div>
                """
            content += '</div>'
        else:
            content += '<div class="metric-card"><p class="status-ok">✅ No errors detected!</p></div>'

        html = self._get_base_html("Errors", content, "errors")
        return web.Response(text=html, content_type='text/html')

    async def dashboard_handler(self, request):
        """Main dashboard"""
        metrics = get_metrics()
        if not metrics:
            return web.Response(text="Metrics not initialized", status=503)

        summary = metrics.get_metrics_summary()

        # Events summary
        events_html = ""
        if summary.get('events'):
            for event, count in list(summary['events'].items())[:5]:
                events_html += f"<li>{event}: <strong>{count}</strong></li>"

        # Errors summary
        errors_html = ""
        if summary.get('errors'):
            for error, count in summary['errors'].items():
                errors_html += f"<li class='status-error'>{error}: <strong>{count}</strong></li>"

        # Conversions
        conversions_html = ""
        if summary.get('conversions'):
            for funnel, rates in summary['conversions'].items():
                conversions_html += f"""
                <div class="metric-card">
                    <div class="metric-label">{funnel.replace('_', ' ').title()}</div>
                    {rates}
                </div>
                """

        content = f"""
        <h2>📈 Real-time Dashboard</h2>

        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-label">System Uptime</div>
                <div class="metric-value">{summary.get('uptime_seconds', 0):.0f}s</div>
            </div>
            <div class="metric-card">
                <div class="metric-label">Last Update</div>
                <div class="metric-value" style="font-size: 1em;">
                    {summary.get('timestamp', 'N/A')}
                </div>
            </div>
        </div>

        <div class="chart">
            <h3>Top Events</h3>
            <ul>{events_html or '<li>No events yet</li>'}</ul>
        </div>

        <div class="chart">
            <h3>Recent Errors</h3>
            <ul>{errors_html or '<li class="status-ok">No errors</li>'}</ul>
        </div>

        {('<div class="chart"><h3>Conversion Funnels</h3>' + conversions_html + '</div>') if conversions_html else ''}
        """

        html = self._get_base_html("Dashboard", content, "dashboard")
        return web.Response(text=html, content_type='text/html')

    async def metrics_json(self, request):
        """Return metrics as formatted JSON"""
        metrics = get_metrics()
        if not metrics:
            return web.json_response({"error": "Metrics not initialized"}, status=503)

        summary = metrics.get_metrics_summary()

        # Pretty print JSON with syntax highlighting
        json_str = json.dumps(summary, indent=2, default=str)

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Metrics JSON</title>
            <style>
                body {{ 
                    background: #1e1e1e; 
                    color: #d4d4d4; 
                    font-family: 'Courier New', monospace;
                    padding: 20px;
                }}
                pre {{ 
                    background: #2d2d2d; 
                    padding: 20px; 
                    border-radius: 10px;
                    overflow: auto;
                }}
                .json-key {{ color: #9cdcfe; }}
                .json-value {{ color: #ce9178; }}
                .json-number {{ color: #b5cea8; }}
            </style>
        </head>
        <body>
            <h1>📊 Raw Metrics JSON</h1>
            <pre>{json_str}</pre>
            <p><a href="/" style="color: #569cd6;">← Back to Overview</a></p>
        </body>
        </html>
        """

        return web.Response(text=html, content_type='text/html')

    async def prometheus_handler(self, request):
        """Prometheus metrics"""
        metrics = get_metrics()
        if not metrics:
            return web.Response(text="# Metrics not initialized", status=503)

        prometheus_data = metrics.export_to_prometheus()

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Prometheus Metrics</title>
            <style>
                body {{ 
                    background: #f5f5f5; 
                    font-family: 'Courier New', monospace;
                    padding: 20px;
                }}
                pre {{ 
                    background: white; 
                    padding: 20px; 
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    overflow: auto;
                }}
            </style>
        </head>
        <body>
            <h1>📈 Prometheus Metrics</h1>
            <pre>{prometheus_data}</pre>
            <p><a href="/">← Back to Overview</a></p>
        </body>
        </html>
        """

        return web.Response(text=html, content_type='text/html')

    async def health_check(self, request):
        """Enhanced health check endpoint"""
        health_status = {
            "status": "healthy",
            "checks": {}
        }

        # Database check with connection pool info
        try:
            db = Database()
            with db.session() as s:
                # Test database connection using SQLAlchemy select
                s.scalar(select(1))

            # Get pool stats with safe attribute access
            pool = db.engine.pool
            pool_stats = {
                "size": getattr(pool, 'size', lambda: 0)(),
                "checked_in": getattr(pool, 'checkedin', lambda: 0)(),
                "checked_out": getattr(pool, 'checkedout', lambda: 0)(),
                "overflow": getattr(pool, 'overflow', lambda: 0)() if hasattr(pool, 'overflow') else 0
            }
            health_status["checks"]["database"] = {
                "status": "ok",
                "pool": pool_stats
            }

            # Check if pool is near exhaustion
            if pool_stats["checked_out"] > pool_stats["size"] * 0.9:
                health_status["checks"]["database"]["warning"] = "connection pool nearly exhausted"
                health_status["status"] = "degraded"

        except Exception as e:
            health_status["checks"]["database"] = f"error: {str(e)}"
            health_status["status"] = "unhealthy"

        # Redis/Cache check (lazy import to avoid circular dependency)
        from bot.caching.cache import get_cache_manager
        cache = get_cache_manager()
        if cache:
            try:
                # Test redis connection
                await cache.get("health_check_test")
                health_status["checks"]["redis"] = "ok"
            except Exception as e:
                health_status["checks"]["redis"] = f"error: {str(e)}"
                health_status["status"] = "degraded"
        else:
            health_status["checks"]["redis"] = "not configured"

        # Metrics system check
        metrics = get_metrics()
        if metrics:
            health_status["checks"]["metrics"] = "ok"
            health_status["uptime"] = metrics.get_metrics_summary()["uptime_seconds"]
        else:
            health_status["checks"]["metrics"] = "not initialized"
            health_status["status"] = "degraded"

        # Bitcoin address pool check - using SQLAlchemy ORM
        try:
            with Database().session() as s:
                result = s.query(func.count(BitcoinAddress.address)).filter(
                    BitcoinAddress.is_used == False
                ).scalar()

                health_status["checks"]["bitcoin_pool"] = {
                    "available": result,
                    "status": "ok" if result >= 10 else "warning" if result >= 5 else "critical"
                }

                if result < 5:
                    health_status["status"] = "degraded"

        except Exception as e:
            health_status["checks"]["bitcoin_pool"] = f"error: {str(e)}"

        # Background tasks check
        try:
            import bot.tasks.reservation_cleaner as cleaner_task
            import bot.tasks.file_watcher as watcher_task

            bg_tasks = {}

            # Check reservation cleaner
            if hasattr(cleaner_task, 'task') and cleaner_task.task:
                bg_tasks["reservation_cleaner"] = "running"
            else:
                bg_tasks["reservation_cleaner"] = "not started"

            # Check file watcher
            if hasattr(watcher_task, 'watcher') and watcher_task.watcher:
                bg_tasks["file_watcher"] = "running"
            else:
                bg_tasks["file_watcher"] = "not started"

            health_status["checks"]["background_tasks"] = bg_tasks

        except Exception as e:
            health_status["checks"]["background_tasks"] = f"error: {str(e)}"

        status_code = 200 if health_status["status"] == "healthy" else 503
        return web.json_response(health_status, status=status_code)

    async def business_metrics_handler(self, request):
        """Business metrics page - orders, inventory, payments, referrals"""
        metrics = get_metrics()
        if not metrics:
            return web.Response(text="Metrics not initialized", status=503)

        # Get analytics from metrics
        customer_journey = metrics.get_customer_journey_analytics()
        referral_analytics = metrics.get_referral_analytics()
        payment_analytics = metrics.get_payment_analytics()
        inventory_analytics = metrics.get_inventory_analytics()

        # Query database for current business state
        try:
            with Database().session() as s:
                # Orders by status - using SQLAlchemy ORM
                order_stats = s.query(
                    Order.order_status,
                    func.count().label('count')
                ).group_by(Order.order_status).all()

                # Active carts count - using SQLAlchemy ORM
                active_carts = s.query(
                    func.count(func.distinct(ShoppingCart.user_id))
                ).scalar() or 0

                # Low inventory items - using SQLAlchemy ORM with computed column
                available_stock = (Goods.stock_quantity - Goods.reserved_quantity).label('available')

                low_inventory = s.query(
                    Goods.name,
                    available_stock,
                    Goods.reserved_quantity.label('reserved')
                ).filter(
                    (Goods.stock_quantity - Goods.reserved_quantity) < 5
                ).order_by(
                    available_stock.asc()
                ).limit(10).all()

        except Exception as e:
            logger.error(f"Error fetching business metrics: {e}")
            order_stats = []
            active_carts = 0
            low_inventory = []

        # Build orders section
        orders_html = '<div class="metric-grid">'
        order_totals = {}
        for status, count in order_stats:
            order_totals[status] = count
            status_class = {
                'delivered': 'status-ok',
                'completed': 'status-ok',
                'confirmed': 'status-ok',
                'reserved': 'status-warning',
                'pending': 'status-warning',
                'cancelled': 'status-error',
                'expired': 'status-error'
            }.get(status, '')

            orders_html += f"""
            <div class="metric-card">
                <div class="metric-label">{status.title()} Orders</div>
                <div class="metric-value {status_class}">{count}</div>
            </div>
            """
        orders_html += '</div>'

        # Customer Journey section
        journey_html = f"""
        <div class="chart">
            <h3>🛒 Cart & Checkout Metrics</h3>
            <div class="metric-grid">
                <div class="metric-card">
                    <div class="metric-label">Active Carts</div>
                    <div class="metric-value">{active_carts}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Cart → Checkout Rate</div>
                    <div class="metric-value">{customer_journey['cart_metrics']['cart_to_checkout_rate']:.1f}%</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Abandoned Carts</div>
                    <div class="metric-value status-warning">{customer_journey['cart_metrics']['abandoned_carts']}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Order Completion Rate</div>
                    <div class="metric-value">{customer_journey['order_metrics']['completion_rate']:.1f}%</div>
                </div>
            </div>
        </div>
        """

        # Payment preferences section
        payment_html = f"""
        <div class="chart">
            <h3>💳 Payment Analytics</h3>
            <div class="metric-grid">
                <div class="metric-card">
                    <div class="metric-label">Bitcoin Payments</div>
                    <div class="metric-value">{payment_analytics['payment_methods']['bitcoin']['count']}</div>
                    <small>{payment_analytics['payment_methods']['bitcoin']['percentage']:.1f}% of total</small>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Cash Payments</div>
                    <div class="metric-value">{payment_analytics['payment_methods']['cash']['count']}</div>
                    <small>{payment_analytics['payment_methods']['cash']['percentage']:.1f}% of total</small>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Bonus Usage Rate</div>
                    <div class="metric-value">{payment_analytics['bonus_usage']['bonus_usage_rate']:.1f}%</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Payment Completion</div>
                    <div class="metric-value">{payment_analytics['completion']['completion_rate']:.1f}%</div>
                </div>
            </div>
        </div>
        """

        # Referral program section
        referral_html = f"""
        <div class="chart">
            <h3>🎁 Referral Program</h3>
            <div class="metric-grid">
                <div class="metric-card">
                    <div class="metric-label">Codes Created</div>
                    <div class="metric-value">{referral_analytics['codes_created']}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Codes Used</div>
                    <div class="metric-value">{referral_analytics['codes_used']}</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Usage Rate</div>
                    <div class="metric-value">{referral_analytics['usage_rate']:.1f}%</div>
                </div>
                <div class="metric-card">
                    <div class="metric-label">Bonuses Paid</div>
                    <div class="metric-value">{referral_analytics['bonuses_paid']}</div>
                </div>
            </div>
        </div>
        """

        # Inventory section
        inventory_html = '<div class="chart"><h3>📦 Low Inventory Alert</h3>'
        if low_inventory:
            inventory_html += '<table><thead><tr><th>Item</th><th>Available</th><th>Reserved</th></tr></thead><tbody>'
            for name, available, reserved in low_inventory:
                alert_class = 'status-error' if available == 0 else 'status-warning'
                inventory_html += f"""
                <tr>
                    <td><strong>{name}</strong></td>
                    <td class="{alert_class}">{available}</td>
                    <td>{reserved}</td>
                </tr>
                """
            inventory_html += '</tbody></table>'
        else:
            inventory_html += '<p class="status-ok">✅ All items have sufficient stock</p>'
        inventory_html += '</div>'

        content = f"""
        <h2>📊 Business Metrics Dashboard</h2>

        <div class="chart">
            <h3>📋 Orders Status</h3>
            {orders_html}
        </div>

        {journey_html}
        {payment_html}
        {referral_html}
        {inventory_html}
        """

        html = self._get_base_html("Business Metrics", content, "business")
        return web.Response(text=html, content_type='text/html')

    async def background_tasks_handler(self, request):
        """Background tasks monitoring page"""
        metrics = get_metrics()
        summary = metrics.get_metrics_summary() if metrics else {}

        tasks_status = []

        # Reservation Cleaner
        try:
            # Check if any asyncio task named 'run_reservation_cleaner' is running
            import asyncio
            current_tasks = asyncio.all_tasks()
            cleaner_running = any(
                'run_reservation_cleaner' in str(task.get_coro())
                for task in current_tasks
            )

            cleaner_status = {
                "name": "Reservation Cleaner",
                "status": "running" if cleaner_running else "not started",
                "description": "Cleans up expired inventory reservations every 60 seconds",
                "metrics": {
                    "orders_expired": summary.get('events', {}).get('order_expired', 0),
                    "inventory_released": summary.get('events', {}).get('inventory_released', 0)
                }
            }
            tasks_status.append(cleaner_status)
        except Exception as e:
            tasks_status.append({
                "name": "Reservation Cleaner",
                "status": f"error: {str(e)}",
                "description": "Could not load task module"
            })

        # File Watcher
        try:
            from bot.tasks.file_watcher import get_file_watcher
            watcher_instance = get_file_watcher()
            is_running = watcher_instance.is_running() if watcher_instance else False

            watcher_status = {
                "name": "Bitcoin Address File Watcher",
                "status": "running" if is_running else "not started",
                "description": "Monitors btc_addresses.txt for changes and reloads addresses",
                "metrics": {}
            }
            tasks_status.append(watcher_status)
        except Exception as e:
            tasks_status.append({
                "name": "File Watcher",
                "status": f"error: {str(e)}",
                "description": "Could not load task module"
            })

        # Cache Scheduler
        try:
            from bot.caching.scheduler import CacheScheduler
            cache_status = {
                "name": "Cache Scheduler",
                "status": "configured",
                "description": "Invalidates stats cache hourly, full cleanup at 3 AM daily",
                "metrics": {}
            }
            tasks_status.append(cache_status)
        except Exception as e:
            tasks_status.append({
                "name": "Cache Scheduler",
                "status": f"error: {str(e)}",
                "description": "Could not load cache scheduler"
            })

        # Build HTML
        content = '<h2>⚙️ Background Tasks Monitor</h2>'

        for task in tasks_status:
            status_class = 'status-ok' if task['status'] == 'running' or task[
                'status'] == 'configured' else 'status-error' if 'error' in task['status'] else 'status-warning'

            metrics_html = ''
            if task.get('metrics'):
                metrics_html = '<ul>'
                for key, value in task['metrics'].items():
                    metrics_html += f'<li>{key.replace("_", " ").title()}: <strong>{value}</strong></li>'
                metrics_html += '</ul>'

            content += f"""
            <div class="chart">
                <h3>{task['name']}</h3>
                <p><strong>Status:</strong> <span class="{status_class}">{task['status'].upper()}</span></p>
                <p>{task['description']}</p>
                {metrics_html}
            </div>
            """

        html = self._get_base_html("Background Tasks", content, "tasks")
        return web.Response(text=html, content_type='text/html')

    async def start(self):
        """Start monitoring server without access logs"""
        try:
            # Disable access logs
            import logging
            logging.getLogger('aiohttp.access').setLevel(logging.WARNING)

            self.runner = web.AppRunner(
                self.app,
                access_log=None  # Disable access logs
            )
            await self.runner.setup()
            site = web.TCPSite(self.runner, self.host, self.port)
            await site.start()
            logger.info(f"Monitoring server started on http://{self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to start monitoring server: {e}")

    async def stop(self):
        """Stop server"""
        if self.runner:
            await self.runner.cleanup()
            logger.info("Monitoring server stopped")
