import os, sys
import xml.etree.ElementTree as ET
from zipfile import ZipFile
import json
#import xy2do
import cProfile
from functools import lru_cache

XMLNS="http://www.moj.go.jp/MINJI/tizuxml"
XMLNS_ZMN="http://www.moj.go.jp/MINJI/tizuzumen"
PRM_NS=0
PRM_NS_ZMN=1
OUT_DELIMITER="\t"


@lru_cache(maxsize=None)
def swns(s):
    return "".join(["{", XMLNS ,"}",s])

@lru_cache(maxsize=None)
def swns_zmn(s):
    return "".join(["{", XMLNS_ZMN ,"}", s])

def NoneToBlank(s):
    return "" if s is None else s

def getText(tree, name):
    if (tree is None):
        return ""
    return NoneToBlank(tree.findtext(swns(name)))

def getText_zmn(tree, name):
    if (tree is None):
        return ""
    return NoneToBlank(tree.findtext(swns_zmn(name)))

def getIdref(ele, name):
    return ele.find(swns(name)).attrib["idref"]

def getXY(tree, name, prm_zmn=PRM_NS):
    if prm_zmn==PRM_NS_ZMN:
        tmp = tree.find(swns_zmn(name))
    else:
        tmp = tree.find(swns(name))
    x = getText_zmn(tmp, "X")
    y = getText_zmn(tmp, "Y")
    return (x,y)

def getYMD(tree, name):
    tmp = tree.find(swns(name))
    y = getText(tmp, "年")
    m = getText(tmp, "月")
    d = getText(tmp, "日")
    return (y,m,d)


###
def extractBasicInfo(root):
    binfo = {}
    binfo["version"] = getText(root,"version")
    binfo["map_name"] = getText(root,"地図名")
    binfo["city_code"] = getText(root,"市区町村コード")
    binfo["city_name"] = getText(root,"市区町村名")
    binfo["coord"] = getText(root, "座標系")
    binfo["soku_han"] = getText(root, '測地系判別')
    binfo["conv_pgm"] = getText(root, '変換プログラム')
    binfo["conv_pgm_ver"] = getText(root, '変換プログラムバージョン')
    binfo["conv_pgm_param"] = getText(root, '変換パラメータバージョン')
    return binfo

def extractPoint(areaarray):
    area_point = areaarray.findall(swns_zmn("GM_Point"))
    pinfo = {}
    for points in area_point:
        point_id = points.attrib["id"]
        dp = points.find(swns_zmn("GM_Point.position"))
        (x,y) = getXY(dp, "DirectPosition", PRM_NS_ZMN)
        pinfo[point_id] = (x,y)
    return pinfo

def extractHikkaitenFromSyudai(syudaiarray, point_info):
    fudekaipointarray = syudaiarray.findall(swns("筆界点"))
    syudai_pointsinfo = []
    for syu in fudekaipointarray: #筆界点
        shape = getIdref(syu, "形状")
        # ?境界標種別?
        syudai_pointsinfo.append({
            'point_no': getText(syu, "点番名"),
            'shape': shape,
            'x': point_info[shape][0],
            'y': point_info[shape][1]} )
        
    return syudai_pointsinfo

def extractKijuntenFromSyudai(syudaiarray, point_info):
    kijunpointarray = syudaiarray.findall(swns("基準点"))
    syudai_kijun_info = []

    for syu in kijunpointarray: #基準点
        shape = getIdref(syu, "形状")
        syudai_kijun_info.append({
            'point_no': getText(syu, "名称"),
            'shape': shape,
            'syubetu': getText(syu, "基準点種別"),
            'maihyo': getText(syu, '埋標区分'),
            'x': point_info[shape][0],
            'y': point_info[shape][1]} )
        
    return syudai_kijun_info

# 主題属性 Curve: 筆界線/仮行政界
def extractSubjCurveInfoFromSyudai(syudaiarray, keystr):
    fudekailinearray = syudaiarray.findall(swns(keystr))
    cnt = 0
    syudai_linesinfo = []    
    for syu in fudekailinearray: #筆界線
        cnt += 1
        syudai_linesinfo.append({
            'shape': getIdref(syu, "形状"),
            'line_type': getText(syu, "線種別")
        })
    return syudai_linesinfo
def extractHikkaisenFromSyudai(syudaiarray):
    return extractSubjCurveInfoFromSyudai(syudaiarray, "筆界線")
def extractGyouseiLineFromSyudai(syudaiarray):
    return extractSubjCurveInfoFromSyudai(syudaiarray, "仮行政界線")



# 空間属性:Curve
def extractCurve_org(areaarray):
    area_curve = areaarray.findall(swns_zmn("GM_Curve"))
    curves_info = []    
    for curve in area_curve:
        curve_id = curve.attrib["id"]
        cv1=curve.find(swns_zmn("GM_Curve.segment"))
        cv2=cv1.find(swns_zmn("GM_LineString"))
        cv3=cv2.find(swns_zmn("GM_LineString.controlPoint"))
        #cv4=cv3.find(swns_zmn("GM_PointArray.column"))
        no=1
        for cv in cv3:
            #directAddress
            (x,y) = getXY(cv, "GM_Position.direct", PRM_NS_ZMN)
            #indireectAddress
            cv5 = cv.find(swns_zmn("GM_Position.indirect"))
            point_id = ""
            if (not cv5 is None):
                point_id=cv5.find(swns_zmn("GM_PointRef.point")).attrib["idref"]
            curves_info.append({
                'curve_id': curve_id,
                'x': x,
                'y': y,
                'point_id': point_id,
                'num': no
            })
            no = no + 1
    return curves_info

def extractCurve(areaarray):
    area_curve = areaarray.findall(swns_zmn("GM_Curve"))
    curves_info = []  

    ptn_outer = f'{swns_zmn("GM_Curve.segment")}/{swns_zmn("GM_LineString")}/{swns_zmn("GM_LineString.controlPoint")}'
    ptn_inner = f'{swns_zmn("GM_Position.indirect")}/{swns_zmn("GM_PointRef.point")}'
    for curve in area_curve:
        curve_id = curve.attrib["id"]
        cv3 = curve.find(ptn_outer)
        #cv4=cv3.find(swns_zmn("GM_PointArray.column"))
        no=1
        for cv in cv3:
            #directAddress
            (x,y) = getXY(cv, "GM_Position.direct", PRM_NS_ZMN)

            #indireectAddress
            point_id = ""
            cv5 = cv.find(ptn_inner)
            if (not cv5 is None):
                point_id=cv5.attrib["idref"]

            # cv5 = cv.find(swns_zmn("GM_Position.indirect"))
            # point_id = ""
            # if (not cv5 is None):
            #     point_id=cv5.find(swns_zmn("GM_PointRef.point")).attrib["idref"]

            curves_info.append({
                'curve_id': curve_id,
                'x': x,
                'y': y,
                'point_id': point_id,
                'num': no
            })
            no = no + 1
    return curves_info

# 空間属性 Surface
def extractSurface(areaarray):
    area_surface = areaarray.findall(swns_zmn("GM_Surface"))
    surface_info = []   
    for surface in area_surface:
        surface_id = surface.attrib["id"]
        sf1 = surface.find(swns_zmn("GM_Surface.patch"))
        sf2 = sf1.find(swns_zmn("GM_Polygon"))
        sf3 = sf2.find(swns_zmn("GM_Polygon.boundary"))
        sf4 = sf3.find(swns_zmn("GM_SurfaceBoundary"))
        sf5 = sf4.find(swns_zmn("GM_SurfaceBoundary.exterior"))
        sf6 = sf5.find(swns_zmn("GM_Ring"))

        no=1 
        for sf in sf6:
            surface_info.append({
                'surface_id': surface_id,
                'line_id': sf.attrib["idref"],
                'num': no
            })
            no = no + 1
    return surface_info


def extractFudeFromSyudai(fudearray):
    fude_info = []
    cnt=0
    for syu in fudearray: #筆
        cnt += 1
        
        fude_info.append({
            'fude_id': syu.attrib["id"],
            'oaza': getText(syu, "大字コード") ,
            'chome': getText(syu, "丁目コード") ,
            'koaza': getText(syu, "小字コード") ,
            'yobi': getText(syu, "予備コード") ,
            'oaza_name': getText(syu, "大字名") ,
            'chome_name': getText(syu, "丁目名") ,
            'koaza_name': getText(syu, "小字名") ,
            'yobi_name': getText(syu, "予備名") ,
            'chiban': getText(syu, "地番") ,
            'shape': getIdref(syu, "形状") ,
            'seido_kbn': getText(syu, "精度区分") ,
            'zahyo_type': getText(syu, "座標値種別")
            # ?? 筆界未定構成筆
        })
    return fude_info


def extractZkk(zkkarray):
    cnt = 0
    zkk_info = []
    zkk_fuderef_info = []
    for zkk in zkkarray:
        cnt += 1
        (xLB,yLB) = getXY(zkk, "左下座標")
        (xLT,yLT) = getXY(zkk, "左上座標")
        (xRB,yRB) = getXY(zkk, "右下座標")
        (xRT,yRT) = getXY(zkk, "右上座標")
        (yMAP,mMAP,dMAP) = getYMD(zkk, "地図作成年月日")
        (ySET,mSET,dSET) = getYMD(zkk, "備付地図年月日")
        zkk_info.append({
            'map_no': getText(zkk, "地図番号"),
            'scale': getText(zkk, "縮尺分母"),
            'unknown_direct_flg': getText(zkk, "方位不明フラグ"),
            'xLB': xLB,
            'yLB': yLB,
            'xLT': xLT,
            'yLT': yLT,
            'xRB': xRB,
            'yRB': yRB,
            'xRT': xRT,
            'yRT': yRT,
            'maptype': getText(zkk, "地図種類"),
            'mapcategory': getText(zkk, "地図分類"),
            'map_material': getText(zkk, "地図材質"),
            'yMAP': yMAP,
            'mMAP': mMAP,
            'dMAP': dMAP,
            'ySET': ySET,
            'mSET': mSET,
            'dSET': dSET
            #?分割図葉tzu?
        })

        fuderef = zkk.findall(swns("筆参照"))
        zkk_fuderef_info = []    
        for fr in fuderef:
            zkk_fuderef_info.append({
                'map_no': getText(zkk, "地図番号"),
                'fude_ref': fr.attrib["idref"]
            })
    return (zkk_info, zkk_fuderef_info)




def make_linestr_for_write(outary):
    return OUT_DELIMITER.join(map(str,outary))

def write_lines(ofh, lines):
    if len(lines) > 0:
        ofh.write("\n".join(lines)+"\n")



def main():
    args = sys.argv
    # param check (todo)
    root_path = args[1]  #カレントを起点としたデータフォルダ名
    exec_name = args[2]  #202404 とか 202308 など公開データ名などを指定
    #outfilename_base="./out3/"
    outfilename_base = args[3]

    #TODO: パラメタ確認処理等丁寧に
    #TODO: 今後は必要なファイルだけopenするよう（個別実行対応への道）
    #TODO: ちゃんとクローズする

    fout_main = open(outfilename_base+f"{exec_name}_01main.tsv", "w")
    fout_points = open(outfilename_base+f"{exec_name}_11points_data.tsv", "w")
    fout_curves = open(outfilename_base+f"{exec_name}_12curves_data.tsv", "w")
    fout_surface = open(outfilename_base+f"{exec_name}_13surface_data.tsv", "w")
    fout_line  = open(outfilename_base+f"{exec_name}_22line_info.tsv", "w")
    fout_fude = open(outfilename_base+f"{exec_name}_23fude_info.tsv", "w")
    fout_zukaku = open(outfilename_base+f"{exec_name}_31zukaku_info.tsv", "w")
    fout_zukaku_ref = open(outfilename_base+f"{exec_name}_32zukaku_ref.tsv", "w")

    files = os.listdir(root_path)
    n=0
    for fn in files:
        base, ext = os.path.splitext(fn)
        if ext!='.zip':
            continue
        #
        with ZipFile(root_path+"/"+fn) as zf:
            with zf.open(zf.namelist()[0]) as fd:
                tree = ET.parse(fd)
                root = tree.getroot()

                #基本情報を変数に保持
                basic_info = extractBasicInfo(root)
                outary = [exec_name, fn, basic_info['city_name'], basic_info['city_code'], basic_info['map_name'], basic_info['coord'], basic_info['version'], basic_info['soku_han'], basic_info['conv_pgm'], basic_info['conv_pgm_ver'], basic_info['conv_pgm_param']]
                write_lines(fout_main, [make_linestr_for_write(outary)])

                #----- POINT ------
                #空間属性から PointをPID->x,y のdictに保持
                areaarray = root.find(swns("空間属性"))
                point_info = extractPoint(areaarray)

                #主題属性から基準点に関する情報を得る（POINTカテゴリ）
                syudaiarray = root.find(swns("主題属性"))
                syudai_kijun_info = extractKijuntenFromSyudai(syudaiarray,point_info)
                lines=[]
                for ski in syudai_kijun_info:
                    outary = [exec_name, fn, ski['point_no'], ski['shape'], ski['x'], ski['y'], ski['syubetu'], ski['maihyo'],'基準点']
                    lines.append(make_linestr_for_write(outary))
                write_lines(fout_points, lines)

                #主題属性から点番名に関する情報を得る（POINTカテゴリ）
                fude_point_info = extractHikkaitenFromSyudai(syudaiarray,point_info)
                lines=[]
                for fpi in fude_point_info:
                    outary = [exec_name, fn, fpi['point_no'], fpi['shape'], fpi['x'], fpi['y'], '', '','筆界点']
                    lines.append(make_linestr_for_write(outary))
                write_lines(fout_points, lines)

                # ------ CURVE ------
                #筆界線(主題属性)
                hikkai_line_info = extractHikkaisenFromSyudai(syudaiarray)
                #仮行政界線
                gyousei_line_info = extractGyouseiLineFromSyudai(syudaiarray)
                lines=[]
                for fpi in hikkai_line_info:
                    outary = [exec_name, fn,  fpi['shape'], fpi['line_type'],"筆界線"]
                    lines.append(make_linestr_for_write(outary))
                for fpi in gyousei_line_info:
                    outary = [exec_name, fn,  fpi['shape'], fpi['line_type'],"仮行政界線"]
                    lines.append(make_linestr_for_write(outary))
                write_lines(fout_line, lines)


                #筆界線(空間属性)
                curve_info = extractCurve(areaarray)
                lines=[]
                for fpi in curve_info:
                    outary = [exec_name, fn,  fpi['curve_id'], fpi['x'], fpi['y'], fpi['point_id'], fpi['num']]
                    lines.append(make_linestr_for_write(outary))
                write_lines(fout_curves, lines)

                # ----- SURFACE -----
                surface_info = extractSurface(areaarray)
                lines=[]
                for fpi in surface_info:
                    outary = [exec_name, fn,  fpi['surface_id'], fpi['line_id'], fpi['num']]
                    lines.append(make_linestr_for_write(outary))
                write_lines(fout_surface, lines)

                # ------ FUDE ------
                #syudaiarray=root.find(swns("主題属性"))
                fudearray = syudaiarray.findall(swns("筆"))
                fude_info = extractFudeFromSyudai(fudearray)
                lines=[]
                for fpi in fude_info:
                    outary = [exec_name, fn,  fpi['fude_id'], fpi['oaza'], fpi['chome'], fpi['koaza'], fpi['yobi'], fpi['oaza_name'], fpi['chome_name'], fpi['koaza_name'], fpi['yobi_name'], fpi['chiban'], fpi['shape'], fpi['seido_kbn'], fpi['zahyo_type']]
                    lines.append(make_linestr_for_write(outary))
                write_lines(fout_fude, lines)
                #?筆界未定構成筆?

                # ------ ZUKAKU ------
                zkkarray = root.findall(swns("図郭"))
                (zkk_info, zkk_fuderef_info) = extractZkk(zkkarray)
                lines=[]
                for fpi in zkk_info:
                    outary = [exec_name, fn, fpi['map_no'], fpi['scale'], fpi['unknown_direct_flg'], fpi['xLB'], fpi['yLB'], fpi['xLT'], fpi['yLT'], fpi['xRB'], fpi['yRB'], fpi['xRT'], fpi['yRT'], fpi['maptype'], fpi['mapcategory'], fpi['map_material'], fpi['yMAP'], fpi['mMAP'], fpi['dMAP'], fpi['ySET'], fpi['mSET'], fpi['dSET']]
                    lines.append(make_linestr_for_write(outary))
                write_lines(fout_zukaku, lines)

                #図郭_筆参照
                lines=[]
                for fpi in zkk_fuderef_info:
                    outary = [exec_name, fn, fpi['map_no'], fpi['fude_ref']]
                    lines.append(make_linestr_for_write(outary))
                write_lines(fout_zukaku_ref, lines)


#cProfile.run('main()')
main()

# 実行例
# sakaik@saty6:/mnt/f/mojxml/比較トライ/12千葉県$ python3 mojxml_extract_pointinfo.py 202404 202404 outtmp
# sakaik@saty6:/mnt/f/mojxml/比較トライ/12千葉県$ python3 mojxml_extract_pointinfo.py 202308 202308 outtmp 
# sakaik@saty6:/mnt/f/mojxml/比較トライ/12千葉県$ python3 mojxml_extract_pointinfo.py 202301 202301 outtmp 