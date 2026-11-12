"""已确认的荷载计算约定。

跟踪支架的截面、檩距和排间距还没有写入。products/qizhuo30/composition.md 只说明产品大方向，不作为生成 BOM 的依据。这里只记下会改变风、雪和组合的决定。
"""

# 地面粗糙度。当前计算用 Exposure C，不从场地类型换算。
EXPOSURE_CATEGORY = "C"

# 速度风压和第 26–30 章的通用体型系数。具体用哪一张表，等产品几何确定后再对。
WIND_PRESSURE = "ASCE 7-16 Chapter 26"
WIND_COEFFICIENTS = "ASCE 7-16 Chapters 26-30"

# 资料表中的雪荷载作为地面雪荷载 pg。屋面雪荷载按第 7 章由 pg 计算。
SNOW_GIVEN_AS = "ground"
SNOW_PROCEDURE = "ASCE 7-16 Chapter 7"

# 这一阶段不计算地震作用，组合里也不加入 E。
INCLUDE_SEISMIC = False

# 组件竖放。跟踪范围是组件与水平面的夹角。
MODULE_ORIENTATION = "Portrait"
TRACKER_TILT_MIN_DEG = 0
TRACKER_TILT_MAX_DEG = 60

# 风荷载取跟踪范围的两端。雪只取 0°：60° 时雪自行滑下，不在组件上积压。
WIND_TILTS_DEG = (0, 60)
SNOW_TILTS_DEG = (0,)

# 荷载组合只用强度设计，ASCE 7-16 第 2.3.1 节。没有活荷载、屋面活荷载、雨和地震，这些项取 0。
COMBINATION_METHOD = "LRFD"
COMBINATION_SECTION = "ASCE 7-16 Section 2.3.1"
