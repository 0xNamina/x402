async def send_opportunity_alert(bot, token, security, source="Unknown"):
    """Universal alert with PRIORITY badge"""
    
    if "10000x" in token.get('potential', ''):
        fire = "🔥🔥🔥🔥"
    elif "1000x" in token.get('potential', ''):
        fire = "🔥🔥🔥"
    elif "100x" in"""
X402 Token Scanner Bot - ULTIMATE VERSION (FIXED)
Triple Scanner: x402 Mesh API + DexScreener + Security
"""

import asyncio
import aiohttp
import os
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime, timedelta
import logging
import re
import json

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== CONFIG =====
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
BASESCAN_API_KEY = os.getenv("BASESCAN_API_KEY", "")

# APIs
X402_TRENDING_API = "https://mesh.heurist.xyz/x402/agents/trending-tokens"
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex"

# Tracking
bot_started = False
scanned_tokens = set()
last_scan_time = {}
scan_stats = {"x402_scans": 0, "dex_scans": 0, "alerts_sent": 0, "tokens_analyzed": 0}

# ===== SECURITY CHECKS =====
async def check_honeypot(session, contract_address):
    """Check honeypot via Honeypot.is API"""
    try:
        url = "https://api.honeypot.is/v2/IsHoneypot"
        params = {"address": contract_address, "chainID": "8453"}
        
        async with session.get(url, params=params, timeout=15) as response:
            if response.status != 200:
                return None, "⚠️ API error"
            
            data = await response.json()
            is_honeypot = data.get("honeypotResult", {}).get("isHoneypot", False)
            buy_tax = data.get("simulationResult", {}).get("buyTax", 0)
            sell_tax = data.get("simulationResult", {}).get("sellTax", 0)
            
            if is_honeypot:
                return False, "🚨 HONEYPOT!"
            if buy_tax > 10 or sell_tax > 10:
                return False, f"⚠️ Tax: {buy_tax:.1f}/{sell_tax:.1f}%"
            
            return True, f"✅ Tax: {buy_tax:.1f}/{sell_tax:.1f}%"
    except Exception as e:
        logger.error(f"Honeypot check error: {e}")
        return None, "⚠️ Timeout"

async def check_liquidity_dex(session, contract_address):
    """Check liquidity via DexScreener"""
    try:
        url = f"{DEXSCREENER_API}/tokens/{contract_address}"
        async with session.get(url, timeout=10) as response:
            if response.status != 200:
                return None, "⚠️ No data", None
            
            data = await response.json()
            pairs = [p for p in data.get("pairs", []) if p.get("chainId") == "base"]
            
            if not pairs:
                return False, "❌ No Base pool", None
            
            main_pair = max(pairs, key=lambda x: float(x.get("liquidity", {}).get("usd", 0)))
            liq_usd = float(main_pair.get("liquidity", {}).get("usd", 0))
            
            if liq_usd < 5000:
                return False, f"⚠️ Low liq: ${liq_usd:,.0f}", main_pair
            return True, f"✅ Liq: ${liq_usd:,.0f}", main_pair
    except Exception as e:
        logger.error(f"Liquidity check error: {e}")
        return None, "⚠️ Failed", None

async def security_scan(contract_address):
    """Quick security scan"""
    checks = []
    passed = 0
    token_info = None
    
    try:
        async with aiohttp.ClientSession() as session:
            hp_safe, hp_msg = await check_honeypot(session, contract_address)
            checks.append(hp_msg)
            if hp_safe: passed += 1
            
            liq_safe, liq_msg, pair_data = await check_liquidity_dex(session, contract_address)
            checks.append(liq_msg)
            if liq_safe: passed += 1
            
            if pair_data:
                token_info = {
                    "price": float(pair_data.get("priceUsd", 0)),
                    "mcap": float(pair_data.get("marketCap", 0)),
                    "liquidity": float(pair_data.get("liquidity", {}).get("usd", 0)),
                    "volume_24h": float(pair_data.get("volume", {}).get("h24", 0)),
                    "dex_url": pair_data.get("url", "")
                }
    except Exception as e:
        logger.error(f"Security scan error: {e}")
        checks.append(f"❌ Scan error")
    
    total = len([c for c in checks if not c.startswith("❌")])
    score = (passed / total * 100) if total > 0 else 0
    
    if score >= 75:
        level, rec = "🟢 LOW RISK", "✅ SAFE"
    elif score >= 50:
        level, rec = "🟡 MEDIUM", "⚠️ CAUTION"
    else:
        level, rec = "🔴 HIGH RISK", "🚨 AVOID"
    
    return {
        "passed": passed,
        "total": total,
        "score": score,
        "level": level,
        "rec": rec,
        "checks": checks,
        "token_info": token_info
    }

# ===== X402 SCANNER =====
async def scan_x402_trending():
    """Scan x402 Mesh API for trending tokens"""
    try:
        async with aiohttp.ClientSession() as session:
            logger.info("🔍 Querying x402 Trending API...")
            
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json"
            }
            
            async with session.get(X402_TRENDING_API, headers=headers, timeout=20) as response:
                if response.status == 404:
                    logger.warning("x402 API not available (404) - continuing with DexScreener only")
                    return []
                
                if response.status != 200:
                    logger.error(f"x402 API returned {response.status}")
                    return []
                
                # API exists but might return empty - that's OK
                scan_stats["x402_scans"] += 1
                return []  # For now, focus on DexScreener
                
    except Exception as e:
        logger.error(f"x402 API error: {e}")
        return []

# ===== DEXSCREENER SCANNER =====
async def scan_dexscreener_trending():
    """Scan DexScreener for NEW Base chain tokens"""
    try:
        async with aiohttp.ClientSession() as session:
            logger.info("🔍 Scanning DexScreener for NEW Base tokens...")
            
            # UPDATED: Search for newest tokens on Base
            search_queries = [
                "base",  # General Base search
            ]
            
            all_found_pairs = []
            
            for query in search_queries:
                try:
                    url = f"{DEXSCREENER_API}/search/?q={query}"
                    logger.info(f"Searching: {query}")
                    
                    async with session.get(url, timeout=15) as response:
                        if response.status == 200:
                            data = await response.json()
                            all_pairs = data.get("pairs", [])
                            
                            # Filter ONLY Base chain
                            base_pairs = [p for p in all_pairs if p.get("chainId") == "base"]
                            
                            if base_pairs:
                                logger.info(f"Found {len(base_pairs)} Base pairs from search '{query}'")
                                all_found_pairs.extend(base_pairs)
                                
                        await asyncio.sleep(1)  # Rate limit
                        
                except Exception as e:
                    logger.error(f"Search '{query}' failed: {e}")
                    continue
            
            if all_found_pairs:
                # Remove duplicates
                unique_pairs = {p.get("pairAddress"): p for p in all_found_pairs}.values()
                logger.info(f"Total unique pairs found: {len(unique_pairs)}")
                return await process_dex_pairs(list(unique_pairs))
            
            # If search fails, try getting latest Base pairs differently
            logger.warning("Search returned no results, trying alternative method...")
            return await scan_latest_base_pairs(session)
            
    except Exception as e:
        logger.error(f"DexScreener error: {e}")
        return []

async def scan_latest_base_pairs(session):
    """Alternative: Scan for latest activity on Base"""
    try:
        logger.info("Trying to get latest Base activity...")
        
        # Try to get any Base token info as starting point
        # Then find related new pairs
        known_base_dexes = [
            "uniswap",
            "aerodrome", 
            "baseswap"
        ]
        
        # Search for each DEX on Base
        all_pairs = []
        for dex in known_base_dexes:
            try:
                url = f"{DEXSCREENER_API}/search/?q={dex}+base"
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        pairs = [p for p in data.get("pairs", []) if p.get("chainId") == "base"]
                        if pairs:
                            logger.info(f"Found {len(pairs)} pairs on {dex}")
                            all_pairs.extend(pairs[:20])  # Take top 20 from each
                            
                await asyncio.sleep(1)
            except:
                continue
        
        if all_pairs:
            unique_pairs = {p.get("pairAddress"): p for p in all_pairs}.values()
            return await process_dex_pairs(list(unique_pairs))
        
        return []
        
    except Exception as e:
        logger.error(f"Latest pairs scan error: {e}")
        return []

async def process_dex_pairs(pairs):
    """Process DexScreener pairs - UPDATED FOR EARLY GEMS"""
    buy_opportunities = []
    
    try:
        scan_stats["dex_scans"] += 1
        
        now = datetime.now().timestamp() * 1000
        day_ago = now - (24 * 60 * 60 * 1000)
        week_ago = now - (7 * 24 * 60 * 60 * 1000)
        
        logger.info(f"Processing {len(pairs)} pairs...")
        
        for pair in pairs:
            try:
                mcap = float(pair.get("marketCap", 0))
                liq = float(pair.get("liquidity", {}).get("usd", 0))
                vol_24h = float(pair.get("volume", {}).get("h24", 0))
                price_change = float(pair.get("priceChange", {}).get("h24", 0))
                created_at = pair.get("pairCreatedAt", 0)
                
                # RELAXED FILTERS FOR EARLY GEMS
                is_very_new = created_at > day_ago  # <24h
                is_new = created_at > week_ago  # <7d
                is_microcap = 100 < mcap < 1000000  # $100 - $1M (wider range)
                has_min_liquidity = liq > 2000  # LOWERED: >$2k (was $10k)
                has_some_volume = vol_24h > 1000  # LOWERED: >$1k (was $5k)
                is_pumping = price_change > 20  # LOWERED: >20% (was 30%)
                
                # PRIORITY 1: Very new + has liquidity
                # PRIORITY 2: Microcap + volume
                # PRIORITY 3: Pumping
                qualifies = False
                priority = "NORMAL"
                
                if is_very_new and has_min_liquidity:
                    qualifies = True
                    priority = "🆕 NEW LAUNCH"
                elif is_microcap and has_min_liquidity and (has_some_volume or is_pumping):
                    qualifies = True
                    priority = "💎 MICROCAP"
                elif is_pumping and has_min_liquidity:
                    qualifies = True
                    priority = "🚀 PUMPING"
                
                if not qualifies:
                    continue
                
                contract = pair.get("baseToken", {}).get("address", "")
                if not contract:
                    continue
                
                scan_stats["tokens_analyzed"] += 1
                
                # Calculate potential based on market cap
                if mcap < 10000:
                    potential = "10000x+ 🚀🚀🚀🚀"
                elif mcap < 50000:
                    potential = "1000-10000x 🚀🚀🚀"
                elif mcap < 100000:
                    potential = "100-1000x 🚀🚀"
                elif mcap < 500000:
                    potential = "10-100x 🚀"
                else:
                    potential = "5-10x"
                
                # Calculate age
                age_hours = (now - created_at) / (1000 * 60 * 60)
                if age_hours < 1:
                    age_str = f"{age_hours*60:.0f}m ago 🔥"
                elif age_hours < 24:
                    age_str = f"{age_hours:.1f}h ago"
                else:
                    age_str = f"{age_hours/24:.1f}d ago"
                
                buy_opportunities.append({
                    "name": pair.get("baseToken", {}).get("name", "Unknown"),
                    "symbol": pair.get("baseToken", {}).get("symbol", "???"),
                    "contract": contract,
                    "type": "dex_trending",
                    "price": float(pair.get("priceUsd", 0)),
                    "mcap": mcap,
                    "liq": liq,
                    "volume_24h": vol_24h,
                    "price_change_24h": price_change,
                    "dex_url": pair.get("url", ""),
                    "potential": potential,
                    "age": age_str,
                    "is_new": is_very_new,
                    "priority": priority,
                    "source": "DexScreener"
                })
                
                logger.info(f"✅ {priority}: {pair.get('baseToken', {}).get('symbol')} - {potential} (${mcap:,.0f})")
            
            except Exception as e:
                logger.error(f"Error processing pair: {e}")
                continue
        
        # Sort by: New first, then by market cap
        buy_opportunities.sort(key=lambda x: (
            0 if x['is_new'] else 1,  # New tokens first
            x['mcap']  # Then by market cap (smallest first)
        ))
        
        return buy_opportunities[:15]  # Return top 15 (was 10)
    
    except Exception as e:
        logger.error(f"Process pairs error: {e}")
        return []

# ===== TELEGRAM ALERTS =====
async def send_opportunity_alert(bot, token, security, source="Unknown"):
    """Enhanced alert with priority and more info"""
    
    if "10000x" in token.get('potential', ''):
        fire = "🔥🔥🔥🔥"
    elif "1000x" in token.get('potential', ''):
        fire = "🔥🔥🔥"
    elif "100x" in token.get('potential', ''):
        fire = "🔥🔥"
    else:
        fire = "🔥"
    
    # Priority badge
    priority = token.get('priority', 'NORMAL')
    new_badge = " 🆕 JUST LAUNCHED!" if token.get('is_new', False) else ""
    
    msg = f"""
{fire} **{priority}**{new_badge} {fire}

💎 **{token['name']} (${token['symbol']})**
📡 Source: {source}

📊 **STATS:**
💰 Price: ${token['price']:.10f}
📈 24h: {token.get('price_change_24h', 0):+.1f}%
💵 MCap: ${token['mcap']:,.0f}
💧 Liq: ${token['liq']:,.0f}
📊 Vol 24h: ${token.get('volume_24h', 0):,.0f}
⏰ Age: {token.get('age', 'N/A')}

🚀 **POTENTIAL: {token.get('potential', 'High')}**

🔗 **BUY NOW:**
{token.get('dex_url', 'N/A')}

📋 **Contract:**
`{token['contract']}`

🛡️ **SECURITY:**
{security['level']} | {security['rec']}
"""
    
    for check in security['checks']:
        msg += f"{check}\n"
    
    msg += f"""
⚡ **Quick Links:**
🔍 Basescan: https://basescan.org/address/{token['contract']}
📊 DexScreener: https://dexscreener.com/base/{token['contract']}

⚠️ **EXTREME RISK WARNING:**
• VERY early stage token!
• Can 1000x or rug to $0
• Only invest <1% of portfolio
• Set stop loss immediately
• Take profits gradually
• ALWAYS DYOR!

NOT financial advice!
"""
    
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=msg,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        logger.info(f"✅ Alert sent: {token['name']} ({priority}) from {source}")
        scan_stats["alerts_sent"] += 1
    except Exception as e:
        logger.error(f"Error sending alert: {e}")

# ===== MAIN SCAN LOOP =====
async def auto_scan_loop(bot):
    """ULTIMATE scanning loop"""
    global scanned_tokens, last_scan_time
    scan_number = 0
    
    logger.info("🚀 ULTIMATE SCANNER STARTED!")
    
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=(
                "🔥 **ULTIMATE SCANNER ONLINE!** 🔥\n\n"
                "Scanning:\n"
                "✅ DexScreener Base\n"
                "✅ Security checks\n\n"
                "Alerts coming soon! 🚀"
            ),
            parse_mode='Markdown'
        )
    except:
        pass
    
    while True:
        try:
            scan_number += 1
            logger.info(f"\n{'='*50}")
            logger.info(f"[SCAN #{scan_number}] STARTING SCAN")
            logger.info(f"{'='*50}")
            
            all_opportunities = []
            
            # Scan x402 (might be empty)
            logger.info("📡 [1/2] Scanning x402 Mesh API...")
            x402_tokens = await scan_x402_trending()
            logger.info(f"✅ x402: Found {len(x402_tokens)} opportunities")
            all_opportunities.extend(x402_tokens)
            
            # Scan DexScreener
            logger.info("📊 [2/2] Scanning DexScreener...")
            dex_tokens = await scan_dexscreener_trending()
            logger.info(f"✅ DexScreener: Found {len(dex_tokens)} opportunities")
            all_opportunities.extend(dex_tokens)
            
            logger.info(f"\n🔍 Processing {len(all_opportunities)} total opportunities...")
            
            for token in all_opportunities:
                token_id = f"{token['type']}_{token['contract']}"
                
                last_alert = last_scan_time.get(token_id, 0)
                now = datetime.now().timestamp()
                
                if now - last_alert < 3600:
                    continue
                
                if token_id not in scanned_tokens or (now - last_alert) > 3600:
                    logger.info(f"🆕 New opportunity: {token['name']} from {token.get('source', 'Unknown')}")
                    
                    security = await security_scan(token['contract'])
                    
                    if security['score'] >= 50:
                        await send_opportunity_alert(bot, token, security, source=token.get('source', 'Unknown'))
                        scanned_tokens.add(token_id)
                        last_scan_time[token_id] = now
                        await asyncio.sleep(3)
                    else:
                        logger.info(f"❌ Rejected: {token['name']} (security: {security['score']:.0f}%)")
            
            if len(scanned_tokens) > 1000:
                scanned_tokens = set(list(scanned_tokens)[-500:])
            
            cutoff = datetime.now().timestamp() - 86400
            last_scan_time = {k: v for k, v in last_scan_time.items() if v > cutoff}
            
            logger.info(f"\n{'='*50}")
            logger.info(f"[SCAN #{scan_number}] COMPLETE")
            logger.info(f"📊 Stats: x402={scan_stats['x402_scans']}, Dex={scan_stats['dex_scans']}")
            logger.info(f"🔔 Alerts sent: {scan_stats['alerts_sent']}")
            logger.info(f"📈 Tokens analyzed: {scan_stats['tokens_analyzed']}")
            logger.info(f"⏰ Next scan in 5 minutes...")
            logger.info(f"{'='*50}\n")
            
            await asyncio.sleep(300)
            
        except Exception as e:
            logger.error(f"❌ Scan loop error: {e}")
            await asyncio.sleep(60)

# ===== BOT COMMANDS =====
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_started
    
    if not bot_started:
        bot_started = True
        await update.message.reply_text(
            "🔥 **X402 SCANNER ACTIVE!** 🔥\n\n"
            "✅ DexScreener Base: ACTIVE\n"
            "✅ Security checks: ACTIVE\n\n"
            "📲 Alerts for:\n"
            "💎 Microcap gems (<$500k)\n"
            "💎 New launches (<24h)\n"
            "💎 High volume tokens\n\n"
            "⚡ Scanner is now ACTIVE 24/7!\n"
            "Use /status for stats 📊",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("✅ Scanner already active!\nUse /status.", parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 **SCANNER STATUS**\n\n"
        f"✅ Status: **ONLINE**\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S UTC')}\n\n"
        f"📈 **Stats:**\n"
        f"🔔 Alerts: {scan_stats['alerts_sent']}\n"
        f"📊 Dex scans: {scan_stats['dex_scans']}\n"
        f"🔍 Analyzed: {scan_stats['tokens_analyzed']}\n"
        f"💎 Tracked: {len(scanned_tokens)}\n\n"
        f"Bot working 24/7! 🚀",
        parse_mode='Markdown'
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cutoff = datetime.now().timestamp() - (6 * 3600)
    recent = len([v for v in last_scan_time.values() if v > cutoff])
    
    await update.message.reply_text(
        f"📈 **STATISTICS**\n\n"
        f"**Lifetime:**\n"
        f"🔔 Alerts: {scan_stats['alerts_sent']}\n"
        f"🔍 Analyzed: {scan_stats['tokens_analyzed']}\n"
        f"📊 Scans: {scan_stats['dex_scans']}\n\n"
        f"**Recent (6h):**\n"
        f"🔔 Alerts: {recent}\n\n"
        f"Keep watching! 👀",
        parse_mode='Markdown'
    )

# ===== MAIN =====
async def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("❌ Missing credentials!")
        return
    
    logger.info("🚀 Starting X402 Scanner...")
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("stats", stats_command))
    
    await app.initialize()
    await app.start()
    
    bot = app.bot
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text="🟢 **SCANNER DEPLOYED**\n\nSend /start to activate! 🚀",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Startup message error: {e}")
    
    await app.updater.start_polling(drop_pending_updates=True)
    
    scan_task = asyncio.create_task(auto_scan_loop(bot))
    
    try:
        await scan_task
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped")
