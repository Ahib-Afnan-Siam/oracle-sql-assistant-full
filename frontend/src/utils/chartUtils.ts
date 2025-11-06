// Determine the best chart type based on data structure
export function determineChartType(columns: string[], rows: any[]): 'bar' | 'line' | 'pie' | 'doughnut' {
  // If rows is an array of arrays, convert to objects first
  const normalizedRows = Array.isArray(rows[0]) 
    ? (rows as (string | number | null)[][]).map(row => {
        const obj: any = {};
        columns.forEach((col, index) => {
          obj[col] = row[index];
        });
        return obj;
      })
    : rows;
  
  console.log('determineChartType - Columns:', columns);
  console.log('determineChartType - Normalized Rows:', normalizedRows);
  
  // Check if data has date/time values (for line charts)
  const hasTimeData = columns.some(col => 
    col.toLowerCase().includes('date') || 
    col.toLowerCase().includes('time') || 
    col.toLowerCase().includes('month')
  );
  
  // Check if data is suitable for pie chart (one category, one metric)
  const isPieCompatible = columns.length === 2 && normalizedRows.length <= 8;
  
  // Default to bar chart for categorical data
  if (hasTimeData) return 'line';
  if (isPieCompatible) return 'pie';
  return 'bar';
}

// Format table data for Chart.js with large dataset optimization
export function formatChartData(columns: string[], rows: any[], chartType: 'bar' | 'line' | 'pie' | 'doughnut') {
  // If rows is an array of arrays, convert to objects first
  const normalizedRows = Array.isArray(rows[0]) 
    ? (rows as (string | number | null)[][]).map(row => {
        const obj: any = {};
        columns.forEach((col, index) => {
          obj[col] = row[index];
        });
        return obj;
      })
    : rows;
  
  console.log('formatChartData - Columns:', columns);
  console.log('formatChartData - Normalized Rows:', normalizedRows);
  console.log('formatChartData - Chart Type:', chartType);
  
  // OPTIMIZATION: For large datasets, sample the data to prevent performance issues
  const maxDataPoints = 1000; // Maximum number of data points to show in charts
  const originalRowCount = normalizedRows.length;
  let processedRows = normalizedRows;
  
  if (originalRowCount > maxDataPoints) {
    // For large datasets, we'll sample the data to improve performance
    const sampleRate = Math.ceil(originalRowCount / maxDataPoints);
    processedRows = normalizedRows.filter((_, index) => index % sampleRate === 0);
    console.log(`formatChartData - Sampled ${processedRows.length} rows from ${originalRowCount} total rows`);
  }
  
  // Find label column (usually first non-numeric column)
  const labelColumn = columns.find(col => 
    processedRows.length > 0 && typeof processedRows[0][col] === 'string'
  ) || columns[0];
  
  // Find data columns (numeric columns)
  const dataColumns = columns.filter(col => 
    col !== labelColumn && 
    processedRows.length > 0 && 
    (typeof processedRows[0][col] === 'number' || !isNaN(parseFloat(processedRows[0][col])))
  );
  
  console.log('formatChartData - Label Column:', labelColumn);
  console.log('formatChartData - Data Columns:', dataColumns);
  
  // Extract labels
  const labels = processedRows.map(row => row[labelColumn]);
  
  // Generate colors
  const generateColors = (count: number) => {
    const colors = [
      'rgba(54, 162, 235, 0.7)', // blue
      'rgba(255, 99, 132, 0.7)',  // red
      'rgba(75, 192, 192, 0.7)',  // green
      'rgba(255, 159, 64, 0.7)',  // orange
      'rgba(153, 102, 255, 0.7)', // purple
      'rgba(255, 205, 86, 0.7)',  // yellow
      'rgba(201, 203, 207, 0.7)'  // grey
    ];
    
    return Array(count).fill(0).map((_, i) => colors[i % colors.length]);
  };
  
  // Create datasets
  const datasets = dataColumns.map((column, index) => {
    const data = processedRows.map(row => {
      const value = row[column];
      const parsed = typeof value === 'number' ? value : parseFloat(value);
      return isNaN(parsed) ? 0 : parsed;
    });
    const colors = generateColors(dataColumns.length);
    
    console.log(`formatChartData - Dataset for ${column}:`, data);
    
    return {
      label: column.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
      data,
      backgroundColor: chartType === 'line' ? colors[index] : 
                      (chartType === 'pie' || chartType === 'doughnut') ? generateColors(data.length) : 
                      colors[index],
      borderColor: chartType === 'line' ? colors[index] : 'rgba(255, 255, 255, 0.8)',
      borderWidth: 1
    };
  });
  
  const result = {
    labels,
    datasets
  };
  
  console.log('formatChartData - Final Result:', result);
  
  return result;
}