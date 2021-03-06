#!/usr/bin/env python
#******************************************************************************
#  Name:     sar_seq.py
#  Purpose:  Perform sequential change detection on multi-temporal, polarimetric SAR imagery 
#            Determine time(s) at which change occurred
#            Condradsen et al. (2015) Accepted for IEEE Transactions on Geoscience and Remote Sensing
#
#  Usage:             
#    python sar_seq.py [-h] [-m] [-d dims] [-s significance] filenamelist enl
#
# MIT License
# 
# Copyright (c) 2016 Mort Canty
# 
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
# 
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
# 
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import numpy as np
from scipy import stats, ndimage
import os, sys, time, getopt, gdal
from subset import subset
from ipyparallel import Client
from osgeo.gdalconst import GA_ReadOnly, GDT_Byte
from tempfile import NamedTemporaryFile

def call_register((fn0,fni,dims)):
    from register import register
    return register(fn0,fni,dims)

def getmat(fn,cols,rows,bands):
#  read 9- 4- or 1-band preprocessed polarimetric matrix files 
#  and return real/complex matrix elements 
    try:
        inDataset1 = gdal.Open(fn,GA_ReadOnly)     
        if bands == 9:
    #      T11 (k1)
            b = inDataset1.GetRasterBand(1)
            k1 = b.ReadAsArray(0,0,cols,rows)
    #      T12  (a1)
            b = inDataset1.GetRasterBand(2)
            a1 = b.ReadAsArray(0,0,cols,rows)
            b = inDataset1.GetRasterBand(3)    
            im = b.ReadAsArray(0,0,cols,rows)
            a1 = (a1 + 1j*im)
    #      T13  (rho1)
            b = inDataset1.GetRasterBand(4)
            rho1 = b.ReadAsArray(0,0,cols,rows)
            b = inDataset1.GetRasterBand(5)
            im = b.ReadAsArray(0,0,cols,rows)
            rho1 = (rho1 + 1j*im)      
    #      T22 (xsi1)
            b = inDataset1.GetRasterBand(6)
            xsi1 = b.ReadAsArray(0,0,cols,rows)    
    #      T23 (b1)        
            b = inDataset1.GetRasterBand(7)
            b1 = b.ReadAsArray(0,0,cols,rows)
            b = inDataset1.GetRasterBand(8)
            im = b.ReadAsArray(0,0,cols,rows)
            b1 = (b1 + 1j*im)      
    #      T33 (zeta1)
            b = inDataset1.GetRasterBand(9)
            zeta1 = b.ReadAsArray(0,0,cols,rows) 
            result = (k1,a1,rho1,xsi1,b1,zeta1)             
        elif bands == 4:
    #      C11 (k1)
            b = inDataset1.GetRasterBand(1)
            k1 = b.ReadAsArray(0,0,cols,rows)
    #      C12  (a1)
            b = inDataset1.GetRasterBand(2)
            a1 = b.ReadAsArray(0,0,cols,rows)
            b = inDataset1.GetRasterBand(3)
            im = b.ReadAsArray(0,0,cols,rows)
            a1 = (a1 + 1j*im)        
    #      C22 (xsi1)
            b = inDataset1.GetRasterBand(4)
            xsi1 = b.ReadAsArray(0,0,cols,rows)  
            result = (k1,a1,xsi1)         
        elif bands == 1:        
    #      C11 (k1)
            b = inDataset1.GetRasterBand(1)
            k1 = b.ReadAsArray(0,0,cols,rows) 
            result = (k1,)
        inDataset1 = None
        return result
    except Exception as e:
        print 'Error: %s  -- Could not read file'%e
        sys.exit(1)   
    
def PV(fns,n,p,cols,rows,bands):
    '''Return p-values for change indices R^ell_j'''
    j = np.float64(len(fns))
    eps = sys.float_info.min
    k = 0.0; a = 0.0; rho = 0.0; xsi = 0.0; b = 0.0; zeta = 0.0
    for fn in fns:
        result = getmat(fn,cols,rows,bands)
        if p==3:
            k1,a1,rho1,xsi1,b1,zeta1 = result
            k1 = n*np.float64(k1)
            a1 = n*np.complex128(a1)
            rho1 = n*np.complex128(rho1)
            xsi1 = n*np.float64(xsi1)
            b1 = n*np.complex128(b1)
            zeta1 = n*np.float64(zeta1)
            k += k1; a += a1; rho += rho1; xsi += xsi1; b += b1; zeta += zeta1  
        elif p==2:
            k1,a1,xsi1 = result
            k1 = n*np.float64(k1)
            a1 = n*np.complex128(a1)
            xsi1 = n*np.float64(xsi1)
            k += k1; a += a1; xsi += xsi1
        elif p==1:
            k1 = n*np.float64(result[0])
            k += k1              
    if p==3: 
        detsumj = k*xsi*zeta + 2*np.real(a*b*np.conj(rho)) - xsi*(abs(rho)**2) - k*(abs(b)**2) - zeta*(abs(a)**2) 
        k -= k1; a -= a1; rho -= rho1; xsi -= xsi1; b -= b1; zeta -= zeta1 
        detsumj1 = k*xsi*zeta + 2*np.real(a*b*np.conj(rho)) - xsi*(abs(rho)**2) - k*(abs(b)**2) - zeta*(abs(a)**2)
        detj = k1*xsi1*zeta1 + 2*np.real(a1*b1*np.conj(rho1)) - xsi1*(abs(rho1)**2) - k1*(abs(b1)**2) - zeta1*(abs(a1)**2)
    elif p==2:
        detsumj = k*xsi - abs(a)**2 
        k -= k1; a -= a1; xsi -= xsi1
        detsumj1 = k*xsi - abs(a)**2
        detj = k1*xsi1 - abs(a1)**2
    elif p==1:
        detsumj = k  
        k -= k1
        detsumj1 = k
        detj = k1    
    detsumj = np.nan_to_num(detsumj)    
    detsumj = np.where(detsumj <= eps,eps,detsumj)
    logdetsumj = np.log(detsumj)
    detsumj1 = np.nan_to_num(detsumj1)
    detsumj1 = np.where(detsumj1 <= eps,eps,detsumj1)
    logdetsumj1 = np.log(detsumj1)
    detj = np.nan_to_num(detj)
    detj = np.where(detj <= eps,eps,detj)
    logdetj = np.log(detj)
#  test statistic    
    lnRj = n*( p*( j*np.log(j)-(j-1)*np.log(j-1.) ) + (j-1)*logdetsumj1 + logdetj - j*logdetsumj )   
    f =p**2
    rhoj = 1 - (2.*p**2 - 1)*(1. + 1./(j*(j-1)))/(6.*p*n)
    omega2j = -(p*p/4.)*(1.-1./rhoj)**2 + (1./(24.*n*n))*p*p*(p*p-1)*(1+(2.*j-1)/(j*(j-1))**2)/rhoj**2   
#  return p-values  
    Z = -2*rhoj*lnRj
    return 1.0 - ((1.-omega2j)*stats.chi2.cdf(Z,[f])+omega2j*stats.chi2.cdf(Z,[f+4]))
                       
def main():  
    usage = '''
Usage:
------------------------------------------------
    python %s [-h] [-s significance] [-m] [-d dims] infile_1,infile_2,...,infile_n outfilename enl
    
    Perform sequential change detection on multi-temporal, polarimetric SAR imagery in covariance or 
    coherency matrix format. 
                  Use -m for a 3x3 median filter on p-values (e.g. for noisy satellite data)
                  Use -d if files are to be co-registered to a subset of the first image, otherwise
                      it is assumed that the images are co-registered and have identical spatial dimensions              
                  infiles are comma-separated, no blank spaces
                  outfilename is without path (will be written to same directory as infile_1)
--------------------------------------------'''%sys.argv[0]

    options,args = getopt.getopt(sys.argv[1:],'hmd:s:')
    medianfilter = False
    dims = None
    significance = 0.01
    for option, value in options: 
        if option == '-h':
            print usage
            return 
        elif option == '-m':
            medianfilter = True 
        elif option == '-d':
            dims = eval(value)
        elif option == '-s':
            significance = eval(value) 
    if len(args) != 3:              
        print 'Incorrect number of arguments'
        print usage
        sys.exit(1)        
    fns = args[0].split(',')    
    outfn = args[1]
    n = np.float64(eval(args[2])) # equivalent number of looks
    k = len(fns)                  # number of images
    
    print '==============================================='
    print '     Multi-temporal SAR Change Detection'
    print '==============================================='
    print time.asctime()
    gdal.AllRegister()   
    start = time.time()    
#  first SAR image   
    try:              
        inDataset1 = gdal.Open(fns[0],GA_ReadOnly)     
        bands = inDataset1.RasterCount                         
        cols = inDataset1.RasterXSize
        rows = inDataset1.RasterYSize    
        bands = inDataset1.RasterCount
    except Exception as e:
        print 'Error: %s  -- Could not read file'%e
        sys.exit(1)    
    if dims is not None:
#  images are not yet co-registered, so subset first image and register the others
        _,_,cols,rows = dims
        args1 = [(fns[0],fns[i],dims) for i in range(1,k)]
        fn0 = subset(fns[0],dims)
        try:
            print ' \nAttempting parallel execution of co-registration ...' 
            start1 = time.time()  
            c = Client()
            print 'available engines %s'%str(c.ids)
            v = c[:]   
            fns = v.map_sync(call_register,args1)
            print 'elapsed time for co-registration: '+str(time.time()-start1) 
        except Exception as e: 
            start1 = time.time()
            print '%s \nFailed, so running sequential co-registration ...'%e
            fns = map(call_register,args1)  
            print 'elapsed time for co-registration: '+str(time.time()-start1)       
        fns.insert(0,fn0)              
#  dimension
    if bands==9:       
        p = 3
    elif bands==4:
        p = 2
    elif bands==1:
        p = 1
    else:
        print 'incorrect number of bands'
        return    
    print ' \nFirst (reference) filename:  %s'%fns[0]
    print 'number of images: %i'%k
    print 'equivalent number of looks: %f'%n
    print 'significance level: %f'%significance
#  output file
    path = os.path.abspath(fns[0])    
    dirn = os.path.dirname(path)
    outfn = dirn + '/' + outfn 
#  create temporary, memory-mapped array of change indices p(Ri<ri)
    mm = NamedTemporaryFile()
    pvarray = np.memmap(mm.name,dtype=np.float64,mode='w+',shape=(k-1,k-1,rows*cols))  
    print 'pre-calculating R and p-values ...' 
    for i in range(k-1):       
        for j in range(i,k-1):
            print 'R(l=%i,j=%i) '%((i+1),(j-i+2)),
            sys.stdout.flush()
            pv = PV(fns[i:j+2],n,p,cols,rows,bands)
            if medianfilter:
                pv = ndimage.filters.median_filter(pv, size = (3,3))
            pvarray[i,j,:] = pv.ravel() 
        print ''
#  map of most recent change occurrences
    cmap = np.zeros((rows*cols),dtype=np.byte)    
#  map of first change occurrence
    smap = np.zeros((rows*cols),dtype=np.byte)
#  change frequency map 
    fmap = np.zeros((rows*cols),dtype=np.byte)
#  bitemporal change maps
    bmap = np.zeros((rows*cols,k-1),dtype=np.byte)  
    for ell in range(k-1):
        for j in range(ell,k-1):
            pv = pvarray[ell,j,:]
            idx = np.where( (pv <= significance) & (cmap == ell) )
            idx1 = np.where( (pv <= significance) & (cmap == 0) )
            fmap[idx] += 1 
            cmap[idx] = j+1 
            bmap[idx,j] = 255 
            smap[idx1] = j+1
#  write to file system    
    cmap = np.reshape(cmap,(rows,cols))
    fmap = np.reshape(fmap,(rows,cols))
    smap = np.reshape(smap,(rows,cols))
    bmap = np.reshape(bmap,(rows,cols,k-1))
    driver = inDataset1.GetDriver() 
    basename = os.path.basename(outfn)
    name, _ = os.path.splitext(basename)
    outfn1=outfn.replace(name,name+'_cmap')
    outDataset = driver.Create(outfn1,cols,rows,1,GDT_Byte)
    geotransform = inDataset1.GetGeoTransform()
    if geotransform is not None:
        outDataset.SetGeoTransform(geotransform)
    projection = inDataset1.GetProjection()        
    if projection is not None:
        outDataset.SetProjection(projection)     
    outBand = outDataset.GetRasterBand(1)
    outBand.WriteArray(cmap,0,0) 
    outBand.FlushCache() 
    print 'most recent change map written to: %s'%outfn1  
    outfn2=outfn.replace(name,name+'_fmap')
    outDataset = driver.Create(outfn2,cols,rows,1,GDT_Byte)
    if geotransform is not None:
        outDataset.SetGeoTransform(geotransform)      
    if projection is not None:
        outDataset.SetProjection(projection)     
    outBand = outDataset.GetRasterBand(1)
    outBand.WriteArray(fmap,0,0) 
    outBand.FlushCache() 
    print 'frequency map written to: %s'%outfn2     
    outfn3=outfn.replace(name,name+'_bmap')
    outDataset = driver.Create(outfn3,cols,rows,k-1,GDT_Byte)
    if geotransform is not None:
        outDataset.SetGeoTransform(geotransform)       
    if projection is not None:
        outDataset.SetProjection(projection)  
    for i in range(k-1):        
        outBand = outDataset.GetRasterBand(i+1)
        outBand.WriteArray(bmap[:,:,i],0,0) 
        outBand.FlushCache() 
    print 'bitemporal map image written to: %s'%outfn3    
    outfn4=outfn.replace(name,name+'_smap')
    outDataset = driver.Create(outfn4,cols,rows,1,GDT_Byte)
    if geotransform is not None:
        outDataset.SetGeoTransform(geotransform)      
    if projection is not None:
        outDataset.SetProjection(projection)     
    outBand = outDataset.GetRasterBand(1)
    outBand.WriteArray(smap,0,0) 
    outBand.FlushCache() 
    print 'first change map written to: %s'%outfn4         
    print 'total elapsed time: '+str(time.time()-start)   
    outDataset = None    
    inDataset1 = None        
    
if __name__ == '__main__':
    main()     